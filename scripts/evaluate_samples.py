#!/usr/bin/env python3
"""Run the Local3D evaluation set against a running ComfyUI server (dev tool; needs Pillow + numpy).

For each prompt: make 4 reference pictures with the Reference Pictures app, score them for reconstruction
friendliness (whole object in frame, plain background, sensible fill), pick the best, then run Image to 3D
(Balanced) with BOTH models and record time and mesh statistics. Results go to a JSONL file; nothing is cherry-picked.

    python scripts/evaluate_samples.py --captures <dir with api_reference_app.json + api_image_app.json> \
        --input-dir <ComfyUI input folder> --output-dir <ComfyUI output folder> --out eval.jsonl
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_presets as bp  # noqa: E402

SAMPLES = [  # (key, category, prompt)
    ("toolbox", "simple hard-surface", "A vintage red metal toolbox with a folding carry handle"),
    ("pocketwatch", "detailed hard-surface", "A detailed steampunk pocket watch with exposed brass gears"),
    ("fox", "organic", "A sleeping fox figurine in glazed white ceramic"),
    ("chair", "thin structures", "A wooden spindle-back chair with thin slender legs"),
    ("basket", "holes / open topology", "A woven wicker basket with an open top and a looped handle"),
    ("teapot", "reflective / metallic", "A polished chrome teapot"),
    ("hat", "fabric-like", "A chunky hand-knitted wool hat with a pom-pom"),
    ("robot", "stylized character", "A cute stylized cartoon robot character, standing"),
]


def score_reference(path: Path) -> dict:
    """Cheap automatic check of the criteria in docs/QUALITY.md (not a quality judgement of the art)."""
    im = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    h, w, _ = im.shape
    ring = np.concatenate([im[:12].reshape(-1, 3), im[-12:].reshape(-1, 3), im[:, :12].reshape(-1, 3), im[:, -12:].reshape(-1, 3)])
    bg = np.median(ring, axis=0)
    bg_noise = float(np.mean(np.std(ring, axis=0)))
    mask = np.linalg.norm(im - bg, axis=2) > 32.0
    ys, xs = np.nonzero(mask)
    if len(ys) < 500:
        return {"ok": False, "reason": "no clear object", "fill": 0.0, "touches_border": False, "bg_noise": bg_noise}
    touches = bool(mask[:6].any() or mask[-6:].any() or mask[:, :6].any() or mask[:, -6:].any())
    fill = float(max(ys.max() - ys.min(), xs.max() - xs.min()) / max(h, w))
    ok = (not touches) and 0.35 <= fill <= 0.92 and bg_noise < 22
    reason = "cropped at the border" if touches else "object too small or too large" if not 0.35 <= fill <= 0.92 else \
        "busy background" if bg_noise >= 22 else ""
    return {"ok": ok, "reason": reason, "fill": round(fill, 2), "touches_border": touches, "bg_noise": round(bg_noise, 1)}


def patch(prompt: dict, title: str, **inputs):
    nid = bp.find(prompt, title)
    prompt[nid]["inputs"].update(inputs)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default="http://127.0.0.1:8199")
    ap.add_argument("--captures", type=Path, required=True)
    ap.add_argument("--input-dir", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("eval.jsonl"))
    ap.add_argument("--only", default="", help="comma list of sample keys")
    args = ap.parse_args()
    ref_cap = json.loads((args.captures / "api_reference_app.json").read_text(encoding="utf-8"))["output"]
    img_cap = json.loads((args.captures / "api_image_app.json").read_text(encoding="utf-8"))["output"]
    only = set(filter(None, args.only.split(",")))

    for i, (key, category, text) in enumerate(SAMPLES):
        if only and key not in only:
            continue
        before = set(args.output_dir.glob("Local3D_reference_*.png"))
        rp = json.loads(json.dumps(ref_cap))
        patch(rp, "Prompt", value=text)
        patch(rp, "Seed", value=100 + i)
        gen = bp.run_once(args.base, rp, args.output_dir)
        new = sorted(set(args.output_dir.glob("Local3D_reference_*.png")) - before)
        scores = [score_reference(p) for p in new]
        pick = next((k for k, s in enumerate(scores) if s["ok"]), 0)
        chosen = args.input_dir / f"eval_{key}.png"
        shutil.copyfile(new[pick], chosen)
        rec = {"key": key, "category": category, "prompt": text, "reference_seconds": gen["seconds"], "candidates": scores,
               "picked": pick + 1, "reference_passes": scores[pick]["ok"], "runs": {}}
        for model in ("Auto", "TRELLIS.2"):
            p = json.loads(json.dumps(img_cap))
            for title, want in (("Quality", "Balanced"), ("Model", model)):
                nid = bp.find(p, title)
                opts = [p[nid]["inputs"][f"option{k}"] for k in range(1, 8) if p[nid]["inputs"].get(f"option{k}")]
                idx = next(k for k, o in enumerate(opts) if o.split()[0] == want)
                p[nid]["inputs"]["choice"], p[nid]["inputs"]["index"] = opts[idx], idx
            patch(p, "Seed", value=7)
            for v in p.values():
                if v["class_type"] == "LoadImage":
                    v["inputs"]["image"] = chosen.name
            rec["runs"]["Pixal3D" if model == "Auto" else "TRELLIS.2"] = bp.run_once(args.base, p, args.output_dir)
        print(json.dumps(rec), flush=True)
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    main()
