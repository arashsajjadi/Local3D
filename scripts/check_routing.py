#!/usr/bin/env python3
"""Check what Auto decides for the evaluation pictures (developer tool; needs a Local3D runtime and the core models).

    python scripts/check_routing.py <runtime_dir> <models_dir> [eval_dir=assets/eval] [--subject Auto|Object|Character|Complex]
                                    [--only name ...] [--keep out.json]

Runs only the subject-routing part of the Image to 3D app (person and face detectors, the decision, the bust cut and the
plain-language report): no 3D generation, a few seconds per picture after the detectors have loaded. Compares the answer
with ``expected.json`` in the evaluation folder and exits 1 when a picture is routed differently.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "local3d_pack" / "example_workflows" / "Local3D_Image_to_3D.app.json"


def set_combo(prompt: dict, title: str, want: str) -> None:
    import bench_presets as bp
    nid = bp.find(prompt, title)
    opts = [prompt[nid]["inputs"][f"option{k}"] for k in range(1, 8) if prompt[nid]["inputs"].get(f"option{k}")]
    idx = next(k for k, o in enumerate(opts) if o.split()[0] == want.split()[0])
    prompt[nid]["inputs"]["choice"], prompt[nid]["inputs"]["index"] = opts[idx], idx


def judge(report: str) -> dict:
    """Pull the decision out of the report text the app shows to the user."""
    first = report.splitlines()[0] if report else ""
    subject = first.split(":", 1)[1].split("(")[0].strip() if ":" in first else "?"
    note = "person" if "Not sure" in report else "toy" if "toy, doll or statue" in report else None
    cut = "cut below the chest" in report
    return {"subject": subject, "note": note, "cut": cut}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runtime")
    ap.add_argument("models")
    ap.add_argument("eval_dir", nargs="?", default=str(ROOT / "assets" / "eval"))
    ap.add_argument("--subject", default="Auto")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--keep")
    ap.add_argument("--port", type=int, default=8331)
    args = ap.parse_args()
    from dev_comfy import Engine   # imported here so that judge() can be used (and tested) without websocket-client

    eval_dir = Path(args.eval_dir)
    expected = json.loads((eval_dir / "expected.json").read_text(encoding="utf-8")) if (eval_dir / "expected.json").exists() else {}
    pictures = sorted(p for p in eval_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if args.only:
        pictures = [p for p in pictures if p.stem in args.only]
    app = json.loads(APP.read_text(encoding="utf-8"))
    work = tempfile.mkdtemp(prefix="l3d_route_")
    results, wrong = {}, []
    with Engine(runtime=args.runtime, models=args.models, workdir=work, port=args.port) as eng:
        api = eng.to_api(app)
        report_id = next(k for k, v in api.items() if v["class_type"] == "PreviewAny" and "report" in (v.get("_meta", {}).get("title") or "").lower())
        for k in [k for k, v in api.items() if v["class_type"] in ("Save3DAdvanced", "Preview3D", "PreviewImage", "SaveImage")]:
            del api[k]
        for k in [k for k, v in api.items() if v["class_type"] == "PreviewAny" and k != report_id]:
            del api[k]
        for pic in pictures:
            shutil.copy(pic, eng.input_dir / pic.name)
            p = json.loads(json.dumps(api))
            set_combo(p, "Subject", args.subject)
            for v in p.values():
                if v["class_type"] == "LoadImage":
                    v["inputs"]["image"] = pic.name
            t0 = time.time()
            res = eng.run(p)
            if res["status"] != "success":
                print(f"{pic.stem:20s} FAILED {str(res.get('messages'))[:300]}")
                wrong.append(pic.stem)
                continue
            text = (res["outputs"].get(report_id) or {}).get("text", [""])[0]
            got = judge(text)
            results[pic.stem] = {"report": text, **got}
            want = expected.get(pic.stem)
            ok = True
            if want and args.subject == "Auto":
                ok = got["subject"].startswith(want["subject"]) and got["note"] == want.get("note")
            print(f"{pic.stem:20s} {got['subject']:16s} note={got['note'] or '-':7s} cut={'yes' if got['cut'] else 'no':3s} "
                  f"{'ok' if ok else 'DIFFERENT from expected ' + json.dumps(want)}  ({time.time() - t0:.1f} s)")
            if not ok:
                wrong.append(pic.stem)
    shutil.rmtree(work, ignore_errors=True)
    if args.keep:
        Path(args.keep).write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print("all as expected" if not wrong else f"{len(wrong)} picture(s) routed differently: {', '.join(wrong)}")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
