#!/usr/bin/env python3
"""Generate the small, legally safe evaluation set for subject routing with FLUX.2 klein 4B (Apache-2.0 weights, so the
pictures can be committed). Dev tool; needs the Prompt to 3D model pack and a Local3D runtime.

    python scripts/make_eval_set.py <runtime_dir> <models_dir> [out_dir=assets/eval]

One picture per kind of subject that routing must tell apart (see docs/CHARACTER_ROUTING_DECISION.md).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dev_comfy import Engine  # noqa: E402
import build_workflows as bw  # noqa: E402

# name -> (expected Auto subject, expected note, prompt). The subject is what a reasonable person would call the picture,
# except where Auto is deliberately cautious: it keeps a person without a clear face (hidden by a beard and hat, or small in a
# full-length figure) and a face without a person (a toy) as Object and says so in a note ("person" / "toy").
SET = {
    "portrait_woman": ("Character bust", None, "studio photograph of an elderly woman with short grey hair and a kind face, head and shoulders portrait, "
                       "plain light grey background, soft even light, sharp focus"),
    "glasses_man": ("Character bust", None, "photograph of a young man with round wire-rimmed glasses and a denim jacket, head and shoulders, "
                    "plain light background, natural light"),
    "raised_hand_woman": ("Character bust", None, "photograph of a smiling woman in a green sweater waving hello with her right hand raised beside her face, "
                          "fingers spread, upper body, plain light background"),
    "comic_wizard": ("Object", "person", "comic book illustration of a bearded wizard in a blue robe casting a spell with one raised hand, "
                     "bold ink lines, flat cel colours, upper body, flat purple background"),
    "full_body_walker": ("Object", "person", "photograph of a man in a grey suit walking, full body from head to shoes, plain light background"),
    "figurine_fox": ("Object", None, "a painted ceramic figurine of a sitting fox, studio product photo, plain light grey background"),
    "toy_astronaut": ("Object", "toy", "a vinyl collectible toy figure of a smiling astronaut, full body, studio product photo, plain light grey background"),
    "bicycle_wheel": ("Object", None, "a bicycle wheel with many thin spokes standing upright, studio product photo, plain light grey background"),
    "fern_plant": ("Object", None, "a potted fern plant with thin feathery leaves, studio photo, plain light grey background"),
    # half-length characters that fill the frame and are cut off by it (the situation of the regression picture); their own seed
    "comic_general": ("Character bust", None, "comic book illustration of a uniformed air force general saluting with his right hand raised to his peaked cap, "
                      "three-quarter view, half-length portrait that fills the frame and is cut off at the belt, bold ink lines, flat cel colours, "
                      "flat purple background", 222),
    "armored_knight": ("Character bust", None, "digital painting of a female knight in polished silver armor raising her clenched right fist, half-length portrait, "
                       "three-quarter view, filling the frame and cut off at the waist, plain dark blue background", 222),
}
DEFAULT_SEED = 20261004


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    runtime, models = sys.argv[1], sys.argv[2]
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).resolve().parent.parent / "assets" / "eval"
    out.mkdir(parents=True, exist_ok=True)
    app = bw.build_reference_app("blackwell")
    work = tempfile.mkdtemp(prefix="l3d_evalset_")
    with Engine(runtime=runtime, models=models, workdir=work, port=8351) as eng:
        api = eng.to_api(app)
        titles = {k: v.get("_meta", {}).get("title") for k, v in api.items()}
        prompt_id = next(k for k, t in titles.items() if t == "Prompt")
        friendly_id = next(k for k, t in titles.items() if t == "3D-friendly reference")
        seed_id = next(k for k, t in titles.items() if t == "Seed")
        batch_id = next(k for k, v in api.items() if v["class_type"] == "EmptyFlux2LatentImage")
        save_id = next(k for k, v in api.items() if v["class_type"] == "SaveImage")
        for name, entry in SET.items():
            text, seed = entry[2], (entry[3] if len(entry) > 3 else DEFAULT_SEED)
            p = json.loads(json.dumps(api))
            p[prompt_id]["inputs"]["value"] = text
            p[friendly_id]["inputs"]["value"] = False
            p[seed_id]["inputs"]["value"] = seed
            p[batch_id]["inputs"]["batch_size"] = 1
            p[save_id]["inputs"]["filename_prefix"] = f"eval/{name}"
            res = eng.run(p)
            if res["status"] != "success":
                print(name, "FAILED", res.get("messages"))
                continue
            img = res["outputs"][save_id]["images"][0]
            from PIL import Image
            im = Image.open(eng.output_path(img)).convert("RGB")
            im.save(out / f"{name}.jpg", quality=88, optimize=True)
            print("made", name, im.size, round((out / f"{name}.jpg").stat().st_size / 1024), "KB", flush=True)
    (out / "expected.json").write_text(json.dumps({k: {"subject": v[0], "note": v[1]} for k, v in SET.items()}, indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "prompts.json").write_text(json.dumps({k: v[2] for k, v in SET.items()}, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
