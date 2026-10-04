#!/usr/bin/env python3
"""Compare 3D-friendly prompt templates by how many generated pictures pass the reconstruction-friendliness check.

Uses the Reference Pictures app through a running server (fast: ~6 s per 4 pictures). For every prompt of the
evaluation set and every template variant it makes several batches and counts the share of pictures that are not cropped at
the border, are a sensible size in frame and have a plain background (see evaluate_samples.score_reference).

    python scripts/evaluate_prompts.py --capture <api_reference_app.json> --output-dir <ComfyUI output> --seeds 3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_presets as bp  # noqa: E402
import evaluate_samples as es  # noqa: E402

VARIANTS = {
    "A: current": ", a single complete object centered in the frame and fully visible with nothing cropped, shown in a "
                  "three-quarter front view from slightly above, soft even studio lighting, plain seamless neutral grey "
                  "background, clean unmarked surfaces, photorealistic 3D render",
    "B: margin": ", a single complete object, small in the frame with a wide empty margin of plain background on every side, "
                 "fully visible and not cropped, three-quarter front view from slightly above, soft even studio lighting, "
                 "seamless neutral grey background, clean unmarked surfaces, photorealistic 3D render",
    "none (raw prompt)": None,
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default="http://127.0.0.1:8199")
    ap.add_argument("--capture", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--out", type=Path, default=Path("prompt_eval.json"))
    args = ap.parse_args()
    cap = json.loads(args.capture.read_text(encoding="utf-8"))["output"]
    results = {}
    for vname, suffix in VARIANTS.items():
        passed = total = 0
        per_prompt = {}
        for key, _cat, text in es.SAMPLES:
            ok = n = 0
            for s in range(args.seeds):
                before = set(args.output_dir.glob("Local3D_reference_*.png"))
                p = json.loads(json.dumps(cap))
                es.patch(p, "Prompt", value=text)
                es.patch(p, "Seed", value=1000 + s)
                friendly = bp.find(p, "3D-friendly reference")
                p[friendly]["inputs"]["value"] = suffix is not None
                if suffix is not None:
                    nid = next(k for k, v in p.items() if v["class_type"] == "StringConcatenate")
                    p[nid]["inputs"]["string_b"] = suffix
                bp.run_once(args.base, p, args.output_dir)
                for img in sorted(set(args.output_dir.glob("Local3D_reference_*.png")) - before):
                    n += 1
                    ok += es.score_reference(img)["ok"]
            per_prompt[key] = f"{ok}/{n}"
            passed, total = passed + ok, total + n
        results[vname] = {"pass_rate": round(passed / total, 3), "passed": passed, "total": total, "per_prompt": per_prompt}
        print(json.dumps({vname: results[vname]}), flush=True)
    args.out.write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
