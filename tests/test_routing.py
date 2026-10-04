"""Subject routing: the Math Expression tables written into the apps make the intended decisions.

The expressions are read back out of the generated app files and evaluated with the same names ComfyUI gives them
(a, b, c, ... = the node's inputs), so a change to data/presets.json or to build_workflows.py that breaks the
routing fails here, without a GPU or a running ComfyUI.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PACK = ROOT / "local3d_pack" / "example_workflows"
IMAGE_APP = json.loads((PACK / "Local3D_Image_to_3D.app.json").read_text(encoding="utf-8"))
PROMPT_APP = json.loads((PACK / "Local3D_Prompt_to_3D.app.json").read_text(encoding="utf-8"))
VIEWS_APP = json.loads((PACK / "Local3D_Character_from_Views.app.json").read_text(encoding="utf-8"))
ROUTING = json.loads((ROOT / "data" / "presets.json").read_text(encoding="utf-8"))["routing"]


def expression(app: dict, title: str) -> str:
    nodes = [n for n in app["nodes"] if n.get("title") == title and n["type"] == "ComfyMathExpression"]
    assert len(nodes) == 1, f"expected exactly one Math Expression titled {title!r}, found {len(nodes)}"
    return nodes[0]["widgets_values"][0]


def evaluate(expr: str, **names):
    """simpleeval in ComfyUI allows min/max/int/float/abs/round; plain eval with just those is equivalent for these tables."""
    allowed = {"min": min, "max": max, "int": int, "float": float, "abs": abs, "round": round}
    return eval(expr, {"__builtins__": {}}, {**allowed, **names})


class SubjectDecision(unittest.TestCase):
    AUTO = expression(IMAGE_APP, "Auto: is it a person?")
    UNSURE = expression(IMAGE_APP, "Unsure about the subject? (Auto only)")

    def auto(self, face, person, face_h, height=1024):
        return evaluate(self.AUTO, a=face, b=person, c=face_h, d=height)

    def test_a_face_and_a_person_is_a_character(self):
        self.assertEqual(self.auto(0.73, 0.93, 245, 1679), 1)           # the officer illustration
        self.assertEqual(self.auto(0.91, 0.96, 380, 1024), 1)           # studio portrait
        self.assertEqual(self.auto(ROUTING["face_score_min"], ROUTING["person_score_min"], 100, 1024), 1)

    def test_a_face_without_a_person_is_a_toy_not_a_character(self):
        self.assertEqual(self.auto(0.90, 0.0, 160, 1024), 0)            # vinyl toy astronaut: face 0.90, person 0.00

    def test_a_close_portrait_needs_no_person(self):
        big = int(ROUTING["portrait_face_fraction"] * 1024) + 5
        self.assertEqual(self.auto(0.9, 0.0, big, 1024), 1)
        self.assertEqual(self.auto(0.9, 0.0, big - 20, 1024), 0)

    def test_a_full_length_figure_stays_an_object(self):
        small = int(ROUTING["bust_min_face_fraction"] * 1600) - 5
        self.assertEqual(self.auto(0.9, 0.95, small, 1600), 0)          # clear face and person, but the face is tiny
        big = int(ROUTING["bust_min_face_fraction"] * 1600) + 5
        self.assertEqual(self.auto(0.9, 0.95, big, 1600), 1)

    def test_no_clear_face_means_object(self):
        self.assertEqual(self.auto(0.0, 0.0, -1, 1024), 0)              # nothing found is reported as 0 / -1
        self.assertEqual(self.auto(0.42, 0.94, 250, 1024), 0)           # comic wizard: face score below the minimum
        self.assertEqual(self.auto(0.2, 0.96, 80, 1024), 0)

    def test_the_subject_control_wins_over_auto(self):
        e = expression(IMAGE_APP, "Subject (resolved)")
        # control index: 0 Auto, 1 Object, 2 Character bust, 3 Complex ; b = what Auto found (0 object, 1 character)
        self.assertEqual(evaluate(e, a=0, b=1), 1)    # Auto + person    -> Character bust
        self.assertEqual(evaluate(e, a=0, b=0), 0)    # Auto + no person -> Object
        self.assertEqual(evaluate(e, a=1, b=1), 0)    # Object chosen    -> Object even with a face
        self.assertEqual(evaluate(e, a=2, b=0), 1)    # Character chosen -> Character even without a face
        self.assertEqual(evaluate(e, a=3, b=1), 2)    # Complex chosen   -> Complex shapes

    def test_model_follows_the_subject_but_an_explicit_model_wins(self):
        e = expression(IMAGE_APP, "Model is TRELLIS.2?")
        # a = Model control (0 Auto, 1 Pixal3D, 2 TRELLIS.2), b = resolved subject (2 = Complex shapes)
        self.assertTrue(evaluate(e, a=0, b=2))        # Auto model + Complex subject -> TRELLIS.2
        self.assertFalse(evaluate(e, a=0, b=0))
        self.assertFalse(evaluate(e, a=0, b=1))       # a character is never silently sent to TRELLIS.2
        self.assertTrue(evaluate(e, a=2, b=0))        # TRELLIS.2 chosen explicitly
        self.assertFalse(evaluate(e, a=1, b=2))       # Pixal3D chosen explicitly beats Complex

    def unsure(self, person, face, control, face_h, height=1024):
        return evaluate(self.UNSURE, a=person, b=face, c=control, d=face_h, e=height)

    def test_the_unsure_notes_only_appear_under_auto(self):
        self.assertEqual(self.unsure(0.9, 0.42, 0, 250), 1)             # a person without a clear face (the comic wizard)
        self.assertEqual(self.unsure(0.9, 0.9, 0, 100, 1600), 1)        # a person with a tiny face: full length
        self.assertEqual(self.unsure(0.9, 0.9, 0, 250), 0)              # a face and a person: not unsure
        self.assertEqual(self.unsure(0.0, 0.9, 0, 160), 2)              # a face without a person: toy, doll or statue
        self.assertEqual(self.unsure(0.0, 0.9, 0, 400), 0)              # ... unless it is a close portrait
        self.assertEqual(self.unsure(0.9, 0.0, 2, 250), 0)              # the user chose: nothing to be unsure about
        self.assertEqual(self.unsure(0.2, 0.0, 0, -1), 0)               # nothing found: just an object

    def test_what_is_unsure_is_exactly_what_auto_leaves_as_object_despite_a_person_or_face(self):
        for person in (0.0, 0.3, 0.7, 0.95):
            for face in (0.0, 0.45, 0.6, 0.95):
                for face_h in (40, 120, 200, 400):
                    auto = self.auto(face, person, face_h, 1000)
                    code = self.unsure(person, face, 0, face_h, 1000)
                    if auto == 1:
                        self.assertEqual(code, 0, (person, face, face_h))     # a character is never also "not sure"
                    if code:
                        self.assertEqual(auto, 0, (person, face, face_h))     # a note only where Auto kept Object


class BustCut(unittest.TestCase):
    GAIN = expression(IMAGE_APP, "Bust cut makes the subject larger for the model?")
    CUT = expression(IMAGE_APP, "Bust cut: last picture row kept")
    # the pictures the rule was measured on: face box (top, height), person box (top, height, width), picture height
    OFFICER = dict(face_y=399, face_h=245, person=(157, 1506, 932), height=1679)   # 937 x 1679 comic, tall
    TALL = dict(face_y=190, face_h=110, person=(60, 1280, 620), height=1344)       # 768 x 1344 three-quarter-length figure
    SQUARE = dict(face_y=170, face_h=170, person=(40, 960, 1000), height=1024)     # 1024 x 1024 half-length figure that fills the frame

    def gain(self, face_y, face_h, person, height):
        py, ph, pw = person
        return evaluate(self.GAIN, a=face_y, b=face_h, c=py, d=ph, e=pw)

    def cut(self, face_y, face_h, height, subject, control=0, person=(0, 1000, 500)):
        py, ph, pw = person
        pays = evaluate(self.GAIN, a=face_y, b=face_h, c=py, d=ph, e=pw)
        return evaluate(self.CUT, a=face_y, b=face_h, c=height, d=subject, e=control, f=pays)

    def test_cutting_pays_for_tall_pictures_and_not_for_square_ones(self):
        self.assertEqual(self.gain(**self.OFFICER), 1)     # 1.6 times larger for the model
        self.assertEqual(self.gain(**self.TALL), 1)        # about 2 times
        self.assertEqual(self.gain(**self.SQUARE), 0)      # the longer side stays the width: no gain
        self.assertEqual(self.gain(0, 100, (0, 500, 800), 600), 0)   # a wide picture: cutting never makes it larger

    def test_the_gain_threshold_is_the_one_in_the_data(self):
        w = 1000
        just_below = int(ROUTING["bust_min_gain"] * w) - 10
        just_above = int(ROUTING["bust_min_gain"] * w) + 10
        # person box top 0, width w; a cut line well inside it: the whole-picture side is max(w, h)
        self.assertEqual(self.gain(100, 100, (0, just_below, w), 5000), 0)
        self.assertEqual(self.gain(100, 100, (0, just_above, w), 5000), 1)

    def test_the_officer_regression_picture(self):
        o = self.OFFICER
        self.assertEqual(self.cut(o["face_y"], o["face_h"], o["height"], 1, person=o["person"]), 1060)   # cut just below the chest

    def test_auto_leaves_a_square_picture_whole_but_an_explicit_choice_cuts_it(self):
        s = self.SQUARE
        self.assertEqual(self.cut(s["face_y"], s["face_h"], s["height"], 1, control=0, person=s["person"]), s["height"])
        cut = self.cut(s["face_y"], s["face_h"], s["height"], 1, control=2, person=s["person"])
        self.assertLess(cut, s["height"])

    def test_only_a_character_is_cut(self):
        o = self.OFFICER
        self.assertEqual(self.cut(o["face_y"], o["face_h"], o["height"], 0, person=o["person"]), o["height"])
        self.assertEqual(self.cut(o["face_y"], o["face_h"], o["height"], 2, person=o["person"]), o["height"])

    def test_no_face_means_no_cut(self):
        self.assertEqual(self.cut(-1, -1, 1679, 1, control=2), 1679)
        self.assertEqual(self.cut(-1, -1, 1679, 1, control=0, person=self.OFFICER["person"]), 1679)

    def test_a_close_portrait_is_never_cut(self):
        self.assertEqual(self.cut(120, 700, 1600, 1, control=2), 1600)    # the cut would fall below the picture

    def test_a_cut_that_only_trims_the_bottom_edge_is_skipped(self):
        self.assertEqual(self.cut(300, 260, 1024, 1, control=2), 1024)    # cut line at row 1002 of 1024: not worth a "bust" crop
        self.assertLess(self.cut(300, 200, 1024, 1, control=2), 1024)

    def test_an_explicit_character_choice_cuts_even_a_small_face(self):
        # Auto leaves full-length figures alone (see SubjectDecision); a user who picks Character bust asked for the bust
        self.assertEqual(self.cut(200, 120, 1600, 1, control=2), 524)

    def test_the_cut_never_goes_above_the_chin(self):
        for face_h in range(150, 400, 25):
            self.assertGreater(self.cut(300, face_h, 3000, 1, control=2), 300 + face_h)


class GraphWiring(unittest.TestCase):
    def test_image_app_crops_before_the_cutout_and_the_framing(self):
        links = {l[0]: l for l in IMAGE_APP["links"]}
        nodes = {n["id"]: n for n in IMAGE_APP["nodes"]}

        def source_of(node_id: int, input_name: str):
            inp = next(i for i in nodes[node_id]["inputs"] if i["name"] == input_name)
            return nodes[links[inp["link"]][1]]["type"]

        self.assertEqual(source_of(192, "image"), "ImageCropV2")          # RemoveBackground sees the bust
        self.assertEqual(source_of(312, "images"), "ImageCropV2")         # so does the framing step
        for n in IMAGE_APP["nodes"]:
            if n.get("title") == "Your cutout (alpha)":
                self.assertEqual(source_of(n["id"], "mask"), "CropMask")  # and the user's own transparency is cropped alike

    def test_the_report_is_an_app_output(self):
        outs = IMAGE_APP["extra"]["linearData"]["outputs"]
        types = {n["id"]: n["type"] for n in IMAGE_APP["nodes"]}
        self.assertIn("PreviewAny", [types[o] for o in outs])
        self.assertIn("Save3DAdvanced", [types[o] for o in outs])

    def test_the_subject_control_is_the_first_choice(self):
        data = IMAGE_APP["extra"]["linearData"]["inputs"]
        titles = {n["id"]: n.get("title") for n in IMAGE_APP["nodes"]}
        self.assertEqual([titles[i[0]] for i in data[:2]], ["Load Image", "Subject"]) if titles[data[0][0]] == "Load Image" else self.assertEqual(titles[data[1][0]], "Subject")

    def test_prompt_app_is_not_affected(self):
        types = {n["type"] for n in PROMPT_APP["nodes"]}
        self.assertNotIn("RTDETR_detect", types)
        self.assertNotIn("MediaPipeFaceLandmarker", types)

    def test_views_app_takes_four_pictures_and_switches_lazily(self):
        loaders = [n for n in VIEWS_APP["nodes"] if n["type"] == "LoadImage"]
        self.assertEqual(sorted(n["title"] for n in loaders), ["Back view", "Front view", "Left view", "Right view"])
        types = [n["type"] for n in VIEWS_APP["nodes"]]
        self.assertEqual(types.count("Pixal3DMultiViewConditioning"), 2)   # four views / front + back
        self.assertEqual(types.count("ComfySwitchNode"), 2)                 # positive + negative
        self.assertNotIn("ImageCropV2", types)                              # no turnaround-sheet slicing any more
        for n in VIEWS_APP["nodes"]:
            if n["type"] == "Pixal3DMultiViewConditioning" and "front + back" in n.get("title", ""):
                names = [i["name"] for i in n["inputs"] if i.get("link") is not None]
                self.assertEqual(sorted(names), ["back", "clip_vision_model", "front"])

    def test_routing_constants_match_the_generated_expressions(self):
        self.assertIn(str(ROUTING["bust_cut_face_heights"]), expression(IMAGE_APP, "Bust cut: last picture row kept"))
        self.assertIn(str(ROUTING["bust_min_gain"]), expression(IMAGE_APP, "Bust cut makes the subject larger for the model?"))
        self.assertIn(str(ROUTING["face_score_min"]), expression(IMAGE_APP, "Auto: is it a person?"))


if __name__ == "__main__":
    unittest.main()
