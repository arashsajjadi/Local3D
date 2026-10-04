#!/usr/bin/env python3
"""Benchmark the Local3D quality presets against a running ComfyUI server (dev tool, stdlib only).

1. Open the app in the frontend and capture its API prompt once (see docs/CONTRIBUTING.md), or reuse a capture.
2. Run:  python scripts/bench_presets.py --capture <api_image_app.json> --image viking.png --out bench.jsonl

Every run uses a different seed so ComfyUI's cache cannot skip the sampling stages; durations are warm-model
timings (models stay loaded between runs). Peak GPU memory is sampled once per second via nvidia-smi and includes
whatever other programs already use the GPU, so ``gpu_delta_mib`` (peak - value before the run) is also reported.
"""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path


def http(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def find(prompt, title):
    return next(k for k, v in prompt.items() if v.get("_meta", {}).get("title") == title)


def glb_stats(path: Path) -> dict:
    b = path.read_bytes()
    jlen = struct.unpack_from("<I", b, 12)[0]
    j = json.loads(b[20:20 + jlen])
    prim = j["meshes"][0]["primitives"][0]
    acc = j["accessors"]
    return {"file": path.name, "mb": round(len(b) / 1e6, 1), "vertices": acc[prim["attributes"]["POSITION"]]["count"],
            "triangles": acc[prim["indices"]]["count"] // 3, "textures": len(j.get("images", []))}


class GpuSampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.samples, self.stop = [], threading.Event()

    def run(self):
        while not self.stop.is_set():
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout.strip()
                self.samples.append((time.time(), int(out.splitlines()[0])))
            except Exception:
                pass
            self.stop.wait(0.5)


def run_once(base: str, prompt: dict, output_dir: Path) -> dict:
    sampler = GpuSampler()
    sampler.start()
    time.sleep(1.2)
    before = sampler.samples[-1][1] if sampler.samples else None
    pid = http(f"{base}/prompt", {"prompt": prompt, "client_id": str(uuid.uuid4())})["prompt_id"]
    rec = None
    while rec is None:
        time.sleep(1.5)
        rec = http(f"{base}/history/{pid}").get(pid)
        if rec and not rec.get("status", {}).get("completed") and rec["status"]["status_str"] != "error":
            rec = None
    sampler.stop.set()
    msgs = {m[0]: m[1] for m in rec["status"]["messages"]}
    t0 = msgs["execution_start"]["timestamp"] / 1000
    t1 = (msgs.get("execution_success") or msgs.get("execution_error"))["timestamp"] / 1000
    peak = max((u for t, u in sampler.samples if t0 - 1 <= t <= t1 + 1), default=None)
    res = {"status": rec["status"]["status_str"], "seconds": round(t1 - t0, 1), "gpu_before_mib": before,
           "gpu_peak_mib": peak, "gpu_delta_mib": (peak - before) if peak and before else None}
    if res["status"] != "success":
        res["error"] = json.dumps(msgs.get("execution_error", {}))[:600]
        return res
    for node in rec["outputs"].values():
        for it in node.get("3d", []) + node.get("result", []):
            if isinstance(it, dict) and it.get("filename", "").endswith(".glb") and it.get("type") == "output":
                res["glb"] = glb_stats(output_dir / it.get("subfolder", "") / it["filename"])
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default="http://127.0.0.1:8199")
    ap.add_argument("--capture", type=Path, required=True, help="API prompt captured from the app (JSON with an 'output' key)")
    ap.add_argument("--image", help="file name inside ComfyUI's input folder")
    ap.add_argument("--output-dir", type=Path, required=True, help="ComfyUI output folder (to read the GLBs)")
    ap.add_argument("--out", type=Path, default=Path("bench.jsonl"))
    ap.add_argument("--fixed-seed", type=int, help="use this seed for every run (to observe ComfyUI's caching between settings)")
    ap.add_argument("--matrix", default="Fast:Auto,Balanced:Auto,Maximum:Auto,Balanced:TRELLIS.2",
                    help="comma list of Quality:Model (Model = first word of the combo label)")
    args = ap.parse_args()
    base_prompt = json.loads(args.capture.read_text(encoding="utf-8"))["output"]

    for i, cell in enumerate(args.matrix.split(",")):
        quality, model = cell.split(":")
        p = json.loads(json.dumps(base_prompt))
        for title, want in (("Quality", quality), ("Model", model)):
            nid = find(p, title)
            opts = [p[nid]["inputs"][f"option{k}"] for k in range(1, 8) if p[nid]["inputs"].get(f"option{k}")]
            idx = next(k for k, o in enumerate(opts) if o.split()[0] == want)
            p[nid]["inputs"]["choice"], p[nid]["inputs"]["index"] = opts[idx], idx
        seed = args.fixed_seed if args.fixed_seed is not None else 5000 + i
        p[find(p, "Seed")]["inputs"]["value"] = seed
        if args.image:
            for v in p.values():
                if v["class_type"] == "LoadImage":
                    v["inputs"]["image"] = args.image
        res = {"quality": quality, "model": model, "seed": seed, **run_once(args.base, p, args.output_dir)}
        print(json.dumps(res), flush=True)
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(res) + "\n")


if __name__ == "__main__":
    main()
