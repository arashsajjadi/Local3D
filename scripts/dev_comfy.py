#!/usr/bin/env python3
"""Developer helper: drive a private ComfyUI engine from Python (start it, convert a UI-format workflow to an API
prompt through the real frontend, queue it, wait, collect the saved files). Used by the evaluation scripts; not shipped.

    from dev_comfy import Engine
    with Engine(runtime=r"<data dir>\\runtime\\ComfyUI_windows_portable", models=r"<models dir>",
                workdir=r"<scratch dir>") as eng:
        api = eng.to_api(ui_workflow_dict)          # runs graphToPrompt in a hidden Edge window
        result = eng.run(api)                       # -> {"seconds": ..., "outputs": {...}, "peak_vram_mib": ..., "peak_torch_vram_mib": ..., "peak_ram_mib": ...}

The engine is started with the same flags Local3D uses (see launcher/Local3D.cs) on a private port.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import websocket  # websocket-client

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


class Engine:
    def __init__(self, runtime: str, models: str, workdir: str, port: int = 8299, pack: str | None = None, extra_args: list[str] | None = None):
        self.runtime, self.models, self.port = Path(runtime), Path(models), port
        self.work = Path(workdir)
        self.pack = Path(pack) if pack else None
        self.extra = extra_args or []
        self.proc = None
        self.edge = None
        self.cdp = None
        self.base = f"http://127.0.0.1:{port}"
        self.input_dir, self.output_dir = self.work / "input", self.work / "output"
        self._gpu: list[int] = []
        self._torch: list[int] = []
        self._rss: list[int] = []
        self._gpu_stop = threading.Event()

    # ---------------------------------------------------------------------------------------------- lifecycle
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self):
        atexit.register(self.stop)   # never leave the engine or the hidden Edge window (and their caches) running
        for d in (self.input_dir, self.output_dir, self.work / "base" / "custom_nodes", self.work / "logs"):
            d.mkdir(parents=True, exist_ok=True)
        if self.pack:
            dest = self.work / "base" / "custom_nodes" / "local3d_pack"
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(self.pack, dest, ignore=shutil.ignore_patterns("variants", "__pycache__"))
        py = self.runtime / "python_embeded" / "python.exe"
        args = [str(py), "-s", "ComfyUI\\main.py", "--windows-standalone-build", "--listen", "127.0.0.1", "--port", str(self.port),
                "--disable-auto-launch", "--disable-all-custom-nodes", "--whitelist-custom-nodes", "local3d_pack",
                "--base-directory", str(self.work / "base"), "--models-directory", str(self.models),
                "--input-directory", str(self.input_dir), "--output-directory", str(self.output_dir)] + self.extra
        env = dict(os.environ, HF_HUB_OFFLINE="1", DO_NOT_TRACK="1", PYTHONUTF8="1")
        log = open(self.work / "logs" / "engine.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(args, cwd=str(self.runtime), env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=0x08000000)
        for _ in range(240):
            time.sleep(1)
            try:
                urllib.request.urlopen(self.base + "/system_stats", timeout=2)
                break
            except Exception:
                if self.proc.poll() is not None:
                    raise RuntimeError("engine exited, see " + str(self.work / "logs" / "engine.log"))
        else:
            raise RuntimeError("engine did not come up")

    def stop(self):
        self._gpu_stop.set()
        if self.cdp:
            try:
                self.cdp.ws.close()
            except Exception:
                pass
        if self.edge:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.edge.pid)], capture_output=True)
        if self.proc and self.proc.poll() is None:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True)

    # ---------------------------------------------------------------------------------------------- frontend conversion
    def _browser(self):
        if self.cdp:
            return self.cdp
        profile = self.work / "edge"
        dbg = self.port + 100
        self.edge = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--enable-unsafe-swiftshader", f"--user-data-dir={profile}",
                                      f"--remote-debugging-port={dbg}", "--window-size=1400,900", "--no-first-run", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        page = None
        for _ in range(60):
            try:
                page = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{dbg}/json/list", timeout=2)) if t["type"] == "page")
                break
            except Exception:
                time.sleep(1)
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=300, suppress_origin=True)
        self.cdp = _Cdp(ws)
        self.cdp.call("Page.enable")
        self.cdp.call("Page.navigate", url=self.base + "/")
        for _ in range(120):
            time.sleep(1)
            if self.cdp.js("(window.app && app.graph && typeof app.graphToPrompt === 'function') || false"):
                break
        time.sleep(2)
        return self.cdp

    def to_api(self, workflow: dict) -> dict:
        """UI-format workflow (a template or an app) -> API prompt, converted by ComfyUI's own frontend."""
        c = self._browser()
        text = json.dumps(workflow)
        res = c.js("(async () => { try { await app.loadGraphData(JSON.parse(%s)); await new Promise(r => setTimeout(r, 1500));"
                   " const p = await app.graphToPrompt(); return JSON.stringify(p.output); } catch (e) { return 'ERR ' + e + ' ' + (e && e.stack || ''); } })()" % json.dumps(text))
        if not isinstance(res, str) or res.startswith("ERR"):
            raise RuntimeError("graphToPrompt failed: " + str(res)[:500])
        return json.loads(res)

    # ---------------------------------------------------------------------------------------------- running
    def _sample_gpu(self):
        """Once a second: total GPU memory in use (all programs), the engine's own torch allocation, and the engine's RAM."""
        try:
            import psutil
            engine = psutil.Process(self.proc.pid)
        except Exception:
            psutil = engine = None
        while not self._gpu_stop.is_set():
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
                self._gpu.append(int(out.split()[0]))
            except Exception:
                pass
            try:
                dev = json.load(urllib.request.urlopen(self.base + "/system_stats", timeout=5))["devices"][0]
                self._torch.append(int((dev["torch_vram_total"] - dev["torch_vram_free"]) / 2**20))
            except Exception:
                pass
            try:
                if engine is not None:
                    procs = [engine] + engine.children(recursive=True)
                    self._rss.append(int(sum(p.memory_info().rss for p in procs if p.is_running()) / 2**20))
            except Exception:
                pass
            self._gpu_stop.wait(1.0)

    def run(self, api: dict, timeout: int = 3600) -> dict:
        self._gpu, self._torch, self._rss, self._gpu_stop = [], [], [], threading.Event()
        sampler = threading.Thread(target=self._sample_gpu, daemon=True)
        sampler.start()
        client_id = uuid.uuid4().hex
        t0 = time.time()
        req = urllib.request.Request(self.base + "/prompt", data=json.dumps({"prompt": api, "client_id": client_id}).encode(), headers={"Content-Type": "application/json"})
        try:
            pid = json.load(urllib.request.urlopen(req, timeout=60))["prompt_id"]
        except urllib.error.HTTPError as e:
            self._gpu_stop.set()
            raise RuntimeError("prompt rejected: " + e.read().decode()[:1500])
        hist = None
        while time.time() - t0 < timeout:
            time.sleep(2)
            h = json.load(urllib.request.urlopen(self.base + f"/history/{pid}", timeout=30))
            if pid in h:
                hist = h[pid]
                break
        self._gpu_stop.set()
        sampler.join(timeout=3)
        if hist is None:
            raise TimeoutError("run did not finish")
        status = hist.get("status", {})
        res = {"seconds": round(time.time() - t0, 1), "status": status.get("status_str"), "outputs": hist.get("outputs", {}),
               "peak_vram_mib": max(self._gpu) if self._gpu else None, "min_vram_mib": min(self._gpu) if self._gpu else None,
               "peak_torch_vram_mib": max(self._torch) if self._torch else None, "peak_ram_mib": max(self._rss) if self._rss else None}
        if status.get("status_str") != "success":
            res["messages"] = [m for m in status.get("messages", []) if m[0] in ("execution_error", "execution_interrupted")]
        return res

    def interrupt(self):
        urllib.request.urlopen(urllib.request.Request(self.base + "/interrupt", data=b"{}", method="POST"), timeout=10)

    def free(self):
        urllib.request.urlopen(urllib.request.Request(self.base + "/free", data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                                                      headers={"Content-Type": "application/json"}), timeout=30)

    def fetch_images(self, outputs: dict, node_ids: list[str], dest: Path, prefix: str = "") -> list[Path]:
        """Download the images that nodes (e.g. PreviewImage) produced in a finished run."""
        dest.mkdir(parents=True, exist_ok=True)
        got = []
        for nid in node_ids:
            for i, img in enumerate((outputs.get(str(nid)) or {}).get("images", [])):
                q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")})
                path = dest / f"{prefix}{nid}_{i}.png"
                path.write_bytes(urllib.request.urlopen(self.base + "/view?" + q, timeout=60).read())
                got.append(path)
        return got

    def output_path(self, entry: dict) -> Path:
        return self.output_dir / entry.get("subfolder", "") / entry["filename"]


class _Cdp:
    def __init__(self, ws):
        self.ws, self.i = ws, 0

    def call(self, method, **params):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})

    def js(self, expr):
        return self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True).get("result", {}).get("value")
