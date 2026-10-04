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
    CUT = expression(IMAGE_APP, "Bust cut: last picture row kept")

    def cut(self, face_y, face_h, height, subject):
        return evaluate(self.CUT, a=face_y, b=face_h, c=height, d=subject)

    def test_the_officer_regression_picture(self):
        # 937 x 1679 comic illustration; MediaPipe face box y=399, height=245  ->  cut just below the chest
        self.assertEqual(self.cut(399, 245, 1679, 1), 1060)

    def test_only_a_character_is_cut(self):
        self.assertEqual(self.cut(399, 245, 1679, 0), 1679)
        self.assertEqual(self.cut(399, 245, 1679, 2), 1679)

    def test_no_face_means_no_cut(self):
        self.assertEqual(self.cut(-1, -1, 1679, 1), 1679)

    def test_a_close_portrait_is_never_cut(self):
        self.assertEqual(self.cut(120, 700, 1600, 1), 1600)    # the cut would fall below the picture

    def test_a_cut_that_only_trims_the_bottom_edge_is_skipped(self):
        self.assertEqual(self.cut(300, 260, 1024, 1), 1024)    # cut line at row 1002 of 1024: not worth a "bust" crop
        self.assertLess(self.cut(300, 200, 1024, 1), 1024)

    def test_an_explicit_character_choice_cuts_even_a_small_face(self):
        # Auto leaves full-length figures alone (see SubjectDecision); a user who picks Character bust asked for the bust
        self.assertEqual(self.cut(200, 120, 1600, 1), 524)

    def test_the_cut_never_goes_above_the_chin(self):
        for face_h in range(150, 400, 25):
            self.assertGreater(self.cut(300, face_h, 3000, 1), 300 + face_h)


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

    def test_routing_constants_match_the_generated_expressions(self):
        self.assertIn(str(ROUTING["bust_cut_face_heights"]), expression(IMAGE_APP, "Bust cut: last picture row kept"))
        self.assertIn(str(ROUTING["face_score_min"]), expression(IMAGE_APP, "Auto: is it a person?"))


if __name__ == "__main__":
    unittest.main()
