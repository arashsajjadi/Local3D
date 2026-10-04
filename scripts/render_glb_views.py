#!/usr/bin/env python3
"""Render a GLB from fixed camera angles (textured and clay) with headless Edge + <model-viewer>. Dev tool for quality evaluation.

    python scripts/render_glb_views.py model.glb out_dir [--size 900] [--views front,left,right,back,q_left,q_right,top]
                                      [--model-viewer path/to/model-viewer.min.js]

``model-viewer`` (Google, Apache-2.0) is downloaded once next to this script's cache folder if no path is given.
Clay renders drop textures and normal maps, so they show the geometry itself (what the 3D model really contains).
Needs ``pip install websocket-client`` and Microsoft Edge.
"""
from __future__ import annotations

import argparse
import base64
import http.server
import json
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import websocket  # websocket-client

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
MODEL_VIEWER_URL = "https://cdn.jsdelivr.net/npm/@google/model-viewer@4.0.0/dist/model-viewer.min.js"
VIEWS = {  # name: (azimuth deg, polar deg)   azimuth 0 = looking at the model's front (+Z)
    "front": (0, 80), "left": (-90, 80), "right": (90, 80), "back": (180, 80),
    "q_left": (-40, 72), "q_right": (40, 72), "top": (0, 25), "bottom": (0, 150),
    # the four views of Pixal3D's multi-view rig: eye level, 90 degrees apart (its "left" is what a camera on the +X side sees)
    "rig_front": (0, 90), "rig_left": (90, 90), "rig_back": (180, 90), "rig_right": (270, 90),
}
PAGE = """<!doctype html><meta charset="utf-8"><style>html,body{margin:0;height:100%;background:#2a2a2e}model-viewer{width:100%;height:100%;--poster-color:transparent}</style>
<script type="module" src="model-viewer.min.js"></script>
<model-viewer id="mv" src="model.glb" exposure="1.1" shadow-intensity="0" environment-image="neutral" camera-orbit="0deg 80deg auto" interaction-prompt="none" camera-target="auto auto auto" field-of-view="auto"></model-viewer>"""


class Cdp:
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


def ensure_model_viewer(path: str | None) -> Path:
    if path:
        return Path(path)
    cache = Path(__file__).resolve().parent.parent / ".cache" / "model-viewer.min.js"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_VIEWER_URL, cache)
    return cache


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("glb")
    ap.add_argument("out")
    ap.add_argument("--size", type=int, default=900)
    ap.add_argument("--views", default="front,left,right,back,q_left,q_right")
    ap.add_argument("--model-viewer")
    ap.add_argument("--no-clay", action="store_true")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--fit", action="store_true", help="place the camera so the whole model fits at --fov (needed for narrow fields of view)")
    ap.add_argument("--fov", type=float, default=28.0, help="vertical field of view in degrees (the multi-view rig uses 20)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="l3d_render_"))
    shutil.copy(args.glb, work / "model.glb")
    shutil.copy(ensure_model_viewer(args.model_viewer), work / "model-viewer.min.js")
    (work / "index.html").write_text(PAGE, encoding="utf-8")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(work), **k)

        def log_message(self, *a):
            pass

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    http_port = srv.server_address[1]
    dbg = 9460
    profile = work / "edge"
    proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--enable-unsafe-swiftshader", "--use-angle=swiftshader",
                             f"--user-data-dir={profile}", f"--remote-debugging-port={dbg}", f"--window-size={args.size},{args.size}",
                             "--hide-scrollbars", "--no-first-run", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        page = None
        for _ in range(60):
            try:
                page = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{dbg}/json/list", timeout=2)) if t["type"] == "page")
                break
            except Exception:
                time.sleep(1)
        c = Cdp(websocket.create_connection(page["webSocketDebuggerUrl"], timeout=180, suppress_origin=True))
        c.call("Page.enable")
        c.call("Emulation.setDeviceMetricsOverride", width=args.size, height=args.size, deviceScaleFactor=1, mobile=False)
        c.call("Page.navigate", url=f"http://127.0.0.1:{http_port}/index.html")
        for _ in range(240):
            time.sleep(1)
            if c.js("(document.getElementById('mv') && document.getElementById('mv').loaded) === true"):
                break
        else:
            print("model did not load", file=sys.stderr)
            return 1
        dims = c.js("(()=>{const d=document.getElementById('mv').getDimensions();const c=document.getElementById('mv').getBoundingBoxCenter();return [d.x,d.y,d.z,c.x,c.y,c.z]})()")
        print("bounding box (m):", [round(v, 3) for v in dims])
        # a slightly wider field of view than "auto" so hands and shoulders are never cropped
        c.js("(()=>{const mv=document.getElementById('mv'); mv.minFieldOfView='10deg'; mv.maxFieldOfView='120deg'; mv.minCameraOrbit='auto auto 0.2m'; mv.maxCameraOrbit='auto auto 30m'; mv.fieldOfView='%sdeg'; return 1})()" % args.fov)

        def shoot(name):
            az, polar = VIEWS[name]
            import math as _m
            radius = "auto"
            if args.fit:
                radius = "%.3fm" % (0.5 * max(dims[0], dims[1]) / _m.tan(_m.radians(args.fov) / 2) * 1.08 + 0.5 * dims[2])
            c.js(f"(()=>{{const mv=document.getElementById('mv'); mv.cameraOrbit='{az}deg {polar}deg {radius}'; mv.jumpCameraToGoal(); return 1}})()")
            time.sleep(2.5)
            data = c.call("Page.captureScreenshot", format="png")["data"]
            path = out / f"{args.prefix}{name}{'_clay' if clay else ''}.png"
            path.write_bytes(base64.b64decode(data))
            print("wrote", path)

        clay = False
        for name in args.views.split(","):
            shoot(name)
        if not args.no_clay:
            c.js("""(()=>{const mv=document.getElementById('mv'); for (const m of mv.model.materials) {
                    m.pbrMetallicRoughness.setBaseColorFactor([0.78,0.78,0.8,1]); m.pbrMetallicRoughness.setMetallicFactor(0); m.pbrMetallicRoughness.setRoughnessFactor(0.85);
                    try { m.pbrMetallicRoughness.baseColorTexture.setTexture(null) } catch(e) {}
                    try { m.pbrMetallicRoughness.metallicRoughnessTexture.setTexture(null) } catch(e) {}
                    try { m.normalTexture.setTexture(null) } catch(e) {}
                    try { m.occlusionTexture.setTexture(null) } catch(e) {} } return 1})()""")
            time.sleep(1.5)
            clay = True
            for name in args.views.split(","):
                shoot(name)
        return 0
    finally:
        proc.terminate()
        srv.shutdown()
        time.sleep(1)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
