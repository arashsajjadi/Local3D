#!/usr/bin/env python3
"""Generate the small, legally safe evaluation set for subject routing with FLUX.2 klein 4B (Apache-2.0 weights, so the
pictures can be committed). Dev tool; needs the Prompt to 3D model pack and a Local3D runtime.

    python scripts/make_eval_set.py <runtime_dir> <models_dir> [out_dir=assets/eval]

One picture per kind of subject that routing must tell apart (see docs/CHARACTER_ROUTING_DECISION.md). ``expected.json`` records
what Auto should answer for each: the subject, the note ("person" or "toy": Auto kept an Object and said why) and whether the
picture is cut to a bust.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_SEED, DEFAULT_SIZE = 20261004, (1024, 1024)
# The subject is what a reasonable person would call the picture, except where Auto is deliberately cautious: it keeps a person
# without a clear face (hidden by a beard and hat, or small in a full-length figure) and a face without a person (a toy) as Object
# and says so in a note. "cut": the bust cut is applied (only where it makes the subject larger for the model: tall pictures).
SET = {
    "portrait_woman": dict(subject="Character bust", note=None, cut=False, prompt=(
        "studio photograph of an elderly woman with short grey hair and a kind face, head and shoulders portrait, "
        "plain light grey background, soft even light, sharp focus")),
    "glasses_man": dict(subject="Character bust", note=None, cut=False, prompt=(
        "photograph of a young man with round wire-rimmed glasses and a denim jacket, head and shoulders, plain light background, natural light")),
    "raised_hand_woman": dict(subject="Character bust", note=None, cut=False, prompt=(
        "photograph of a smiling woman in a green sweater waving hello with her right hand raised beside her face, fingers spread, upper body, "
        "plain light background")),
    "comic_wizard": dict(subject="Object", note="person", cut=False, prompt=(
        "comic book illustration of a bearded wizard in a blue robe casting a spell with one raised hand, bold ink lines, flat cel colours, "
        "upper body, flat purple background")),
    "full_body_walker": dict(subject="Object", note="person", cut=False, prompt=(
        "photograph of a man in a grey suit walking, full body from head to shoes, plain light background")),
    "figurine_fox": dict(subject="Object", note=None, cut=False, prompt=(
        "a painted ceramic figurine of a sitting fox, studio product photo, plain light grey background")),
    "toy_astronaut": dict(subject="Object", note="toy", cut=False, prompt=(
        "a vinyl collectible toy figure of a smiling astronaut, full body, studio product photo, plain light grey background")),
    "bicycle_wheel": dict(subject="Object", note=None, cut=False, prompt=(
        "a bicycle wheel with many thin spokes standing upright, studio product photo, plain light grey background")),
    "fern_plant": dict(subject="Object", note=None, cut=False, prompt=(
        "a potted fern plant with thin feathery leaves, studio photo, plain light grey background")),
    # half-length characters that fill the frame and are cut off by it (the situation of the regression picture); their own seeds.
    # In a SQUARE picture cutting would not make the subject larger for the model, so Auto leaves it whole; in a TALL one it does.
    "comic_general": dict(subject="Character bust", note=None, cut=False, seed=222, prompt=(
        "comic book illustration of a uniformed air force general saluting with his right hand raised to his peaked cap, three-quarter view, "
        "half-length portrait that fills the frame and is cut off at the belt, bold ink lines, flat cel colours, flat purple background")),
    "armored_knight": dict(subject="Character bust", note=None, cut=False, seed=222, prompt=(
        "digital painting of a female knight in polished silver armor raising her clenched right fist, half-length portrait, three-quarter view, "
        "filling the frame and cut off at the waist, plain dark blue background")),
    "comic_general_tall": dict(subject="Character bust", note=None, cut=True, seed=222, size=(768, 1344), prompt=(
        "comic book illustration of a uniformed air force general saluting with his right hand raised to his peaked cap, three-quarter view, "
        "tall vertical composition, three-quarter-length portrait down to the thighs that fills the frame and is cut off by the bottom edge, "
        "bold ink lines, flat cel colours, flat purple background")),
    "armored_knight_tall": dict(subject="Character bust", note=None, cut=True, seed=333, size=(768, 1344), prompt=(
        "digital painting of a female knight in polished silver armor raising her clenched right fist, three-quarter view, tall vertical composition, "
        "three-quarter-length portrait down to the thighs that fills the frame and is cut off by the bottom edge, plain dark blue background")),
}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    from dev_comfy import Engine   # imported here so that SET can be read without websocket-client
    import build_workflows as bw
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
            width, height = entry.get("size", DEFAULT_SIZE)
            p = json.loads(json.dumps(api))
            p[prompt_id]["inputs"]["value"] = entry["prompt"]
            p[friendly_id]["inputs"]["value"] = False
            p[seed_id]["inputs"]["value"] = entry.get("seed", DEFAULT_SEED)
            p[batch_id]["inputs"].update(batch_size=1, width=width, height=height)
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
    expected = {k: {"subject": v["subject"], "note": v["note"], "cut": v["cut"]} for k, v in SET.items()}
    (out / "expected.json").write_text(json.dumps(expected, indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "prompts.json").write_text(json.dumps({k: v["prompt"] for k, v in SET.items()}, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
