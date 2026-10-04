"""The evaluation pictures in assets/eval and the tool that checks them stay consistent (no GPU needed)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

EVAL = ROOT / "assets" / "eval"
EXPECTED = json.loads((EVAL / "expected.json").read_text(encoding="utf-8"))
PROMPTS = json.loads((EVAL / "prompts.json").read_text(encoding="utf-8"))
PICTURES = sorted(p.stem for p in EVAL.glob("*.jpg"))


def jpeg_size(path: Path) -> tuple[int, int]:
    """(width, height) of a JPEG from its start-of-frame marker (no imaging library needed)."""
    data = path.read_bytes()
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    raise ValueError(f"{path} has no start-of-frame marker")


class EvaluationSet(unittest.TestCase):
    def test_every_picture_has_an_expected_answer_and_a_prompt(self):
        self.assertEqual(sorted(EXPECTED), PICTURES)
        self.assertEqual(sorted(PROMPTS), PICTURES)

    def test_expected_answers_use_known_values(self):
        for name, want in EXPECTED.items():
            self.assertIn(want["subject"], ("Object", "Character bust", "Complex"), name)
            self.assertIn(want["note"], (None, "person", "toy"), name)
            self.assertIsInstance(want["cut"], bool, name)
            if want["subject"] == "Character bust":
                self.assertIsNone(want["note"], name)   # Auto never calls a subject a character and unsure at once
            else:
                self.assertFalse(want["cut"], name)     # only a character is cut

    def test_expected_answers_match_the_definition_in_make_eval_set(self):
        import make_eval_set
        self.assertEqual({k: {"subject": v["subject"], "note": v["note"], "cut": v["cut"]} for k, v in make_eval_set.SET.items()}, EXPECTED)
        self.assertEqual({k: v["prompt"] for k, v in make_eval_set.SET.items()}, PROMPTS)

    def test_pictures_have_the_size_they_were_made_with(self):
        import make_eval_set
        for name, entry in make_eval_set.SET.items():
            self.assertEqual(jpeg_size(EVAL / f"{name}.jpg"), entry.get("size", make_eval_set.DEFAULT_SIZE), name)

    def test_the_set_covers_each_kind_of_subject(self):
        subjects = {w["subject"] for w in EXPECTED.values()}
        notes = {w["note"] for w in EXPECTED.values()}
        self.assertTrue({"Object", "Character bust"} <= subjects)
        self.assertTrue({"person", "toy"} <= notes)
        cuts = {w["cut"] for w in EXPECTED.values()}
        self.assertEqual(cuts, {True, False})            # a tall picture that is cut and square ones that stay whole

    def test_pictures_are_small_enough_to_keep_in_the_repository(self):
        for p in EVAL.glob("*.jpg"):
            self.assertLess(p.stat().st_size, 400_000, p.name)


class ReadingTheReport(unittest.TestCase):
    def setUp(self):
        import check_routing
        self.judge = check_routing.judge

    def test_a_character_report(self):
        got = self.judge("Subject: Character bust (Auto picked it)\nLooked for: a face (score 0.73) and a person (score 0.93); scores run from 0 to 1.\n"
                         "Framing: cut below the chest, rows 0 to 1059 of 1679 kept, so the face and hands get more detail.\n"
                         "Hidden surfaces (the back and the far side) are inferred, not measured.")
        self.assertEqual(got, {"subject": "Character bust", "note": None, "cut": True})

    def test_the_two_kinds_of_note(self):
        person = self.judge("Subject: Object (Auto picked it)\nFraming: the whole picture\nNot sure: a person, but no large clear face (it may be hidden).")
        toy = self.judge("Subject: Object (Auto picked it)\nFraming: the whole picture\nNote: a face but no person, so this may be a toy, doll or statue.")
        plain = self.judge("Subject: Object (your choice)\nFraming: the whole picture\n")
        self.assertEqual((person["note"], toy["note"], plain["note"]), ("person", "toy", None))
        self.assertEqual(plain["subject"], "Object")


if __name__ == "__main__":
    unittest.main()
