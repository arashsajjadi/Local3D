#!/usr/bin/env python3
"""Capture README screenshots (and optionally a GIF) from the REAL Local3D window over the DevTools protocol.

Dev tool; needs `pip install websocket-client pillow`. Start Local3D with a debugging port first:

    set LOCAL3D_BROWSER_ARGS=--remote-debugging-port=9333
    Local3D.exe

    python scripts/capture_media.py shot docs/images/app-image-ready.png
    python scripts/capture_media.py run  docs/images/demo.gif --prefix docs/images/app
    python scripts/capture_media.py app  docs/images/app-prompt-ready.png --template Local3D_Prompt_to_3D.app
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
import urllib.request

import websocket  # websocket-client
from PIL import Image


class Page:
    def __init__(self, port: int, width: int = 1440, height: int = 900):
        targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10))
        page = next(t for t in targets if t["type"] == "page" and t["url"].startswith("http://127.0.0.1"))
        self.base = page["url"].split("/?")[0].split("/#")[0]
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
        self._id = 0
        self.call("Page.enable")
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)

    def call(self, method: str, **params):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr: str):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        return r.get("result", {}).get("value")

    def png(self) -> Image.Image:
        data = self.call("Page.captureScreenshot", format="png")["data"]
        return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")

    def wait_ready(self, timeout: float = 90):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.js("(window.app && app.graph && app.graph.nodes.length > 10) || false"):
                time.sleep(1.5)
                return
            time.sleep(1)
        raise TimeoutError("app did not load")

    def click_text(self, text: str) -> bool:
        return bool(self.js(
            "(() => { const b = [...document.querySelectorAll('button')].find(x => x.textContent.trim() === %s);"
            " if (!b) return false; b.click(); return true; })()" % json.dumps(text)))

    def queue_idle(self) -> bool:
        return bool(self.js("fetch('/queue').then(r => r.json()).then(q => q.queue_running.length + q.queue_pending.length === 0)"))

    def drag(self, x0, y0, x1, y1, steps=12):
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0, button="left", clickCount=1)
        for i in range(1, steps + 1):
            self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + (x1 - x0) * i / steps, y=y0 + (y1 - y0) * i / steps, buttons=1)
            yield i
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x1, y=y1, button="left")


def save_gif(frames: list[Image.Image], path: str, width: int = 880, first_ms=1500, ms=170, last_ms=2800, max_frames: int = 34):
    import numpy as np
    kept = [frames[0]]
    for f in frames[1:]:
        if float(np.abs(np.asarray(f.resize((160, 100))).astype(np.int16) - np.asarray(kept[-1].resize((160, 100))).astype(np.int16)).mean()) > 0.8:
            kept.append(f)
    if len(kept) > max_frames:   # keep the first and the last few, thin the middle
        step = (len(kept) - 6) / (max_frames - 6)
        kept = kept[:1] + [kept[1 + int(i * step)] for i in range(max_frames - 6)] + kept[-5:]
    small = [f.resize((width, int(f.height * width / f.width)), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=64) for f in kept]
    durations = [first_ms] + [ms] * (len(small) - 2) + [last_ms]
    small[0].save(path, save_all=True, append_images=small[1:], duration=durations, loop=0, optimize=True, disposal=2)
    return len(small)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("mode", choices=["shot", "run", "app"])
    ap.add_argument("out")
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--prefix", default="")
    ap.add_argument("--template", default="Local3D_Prompt_to_3D.app", help="for mode 'app': which app to open")
    args = ap.parse_args()
    page = Page(args.port)
    if args.mode == "app":
        page.call("Page.navigate", url=f"{page.base}/?template={args.template}&source=local3d_pack&mode=linear")
        time.sleep(4)
    page.wait_ready()
    if args.mode in ("shot", "app"):
        page.png().save(args.out)
        print("saved", args.out)
        return
    frames = [page.png()]
    frames[0].save(f"{args.prefix}-ready.png")
    if not page.click_text("Run"):
        sys.exit("could not find the Run button")
    t0, k = time.time(), 0
    while time.time() - t0 < 600:
        time.sleep(1.0)
        k += 1
        if k % 2 == 0:
            frames.append(page.png())
        if k > 3 and page.queue_idle():
            break
    time.sleep(4)
    done = page.png()
    done.save(f"{args.prefix}-result.png")
    frames.append(done)
    # orbit the result a little so the GIF shows that the model is interactive (drag inside the viewer)
    for _ in page.drag(560, 420, 560, 420, steps=1):
        pass
    x = 560
    page.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=430, button="left", clickCount=1)
    for k in range(1, 9):
        page.call("Input.dispatchMouseEvent", type="mouseMoved", x=x + k * 22, y=430, buttons=1)
        time.sleep(0.25)
        frames.append(page.png())
    page.call("Input.dispatchMouseEvent", type="mouseReleased", x=x + 8 * 22, y=430, button="left")
    n = save_gif(frames, args.out)
    print("saved", args.out, n, "frames")


if __name__ == "__main__":
    main()
