"""The validator must catch the mistakes it exists to catch."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import validate  # noqa: E402

APP = json.loads((ROOT / "local3d_pack" / "example_workflows" / "Local3D_Image_to_3D.app.json").read_text(encoding="utf-8"))
CORE = json.loads((ROOT / "data" / "core_node_types.json").read_text(encoding="utf-8"))
CORE_TYPES = set(CORE["node_types"]) | set(CORE["frontend_only"])


def problems(fn, *args):
    validate.errors.clear()
    fn(*args)
    return list(validate.errors)


class GraphChecks(unittest.TestCase):
    def test_shipped_app_is_clean(self):
        self.assertEqual(problems(validate.check_graph, "app", APP, CORE_TYPES), [])
        self.assertEqual(problems(validate.check_app, "app", APP), [])

    def test_custom_node_is_rejected(self):
        d = copy.deepcopy(APP)
        d["nodes"][0]["type"] = "SomeCommunityNode"
        self.assertTrue(any("not a Comfy Core node" in e for e in problems(validate.check_graph, "app", d, CORE_TYPES)))

    def test_dangling_link_is_rejected(self):
        d = copy.deepcopy(APP)
        d["links"].append([99999, 1, 0, 424242, 0, "IMAGE"])
        self.assertTrue(problems(validate.check_graph, "app", d, CORE_TYPES))

    def test_unregistered_link_is_rejected(self):
        d = copy.deepcopy(APP)
        for n in d["nodes"]:
            for i in n.get("inputs", []):
                if i.get("link") is not None:
                    i["link"] = None
                    break
            else:
                continue
            break
        self.assertTrue(problems(validate.check_graph, "app", d, CORE_TYPES))

    def test_unsupported_schema_is_rejected(self):
        d = copy.deepcopy(APP)
        d["version"] = 1
        self.assertTrue(any("schema version" in e for e in problems(validate.check_graph, "app", d, CORE_TYPES)))


class AppChecks(unittest.TestCase):
    def test_not_an_app(self):
        d = copy.deepcopy(APP)
        d["extra"]["linearMode"] = False
        self.assertTrue(any("linearMode" in e for e in problems(validate.check_app, "app", d)))

    def test_long_description_is_rejected(self):
        d = copy.deepcopy(APP)
        d["extra"]["linearData"]["inputs"][0][2] = {"description": "x" * 80}
        self.assertTrue(any("one line" in e for e in problems(validate.check_app, "app", d)))

    def test_muted_input_is_rejected(self):
        d = copy.deepcopy(APP)
        nid = d["extra"]["linearData"]["inputs"][1][0]
        next(n for n in d["nodes"] if n["id"] == nid)["mode"] = 2
        self.assertTrue(any("muted" in e for e in problems(validate.check_app, "app", d)))

    def test_preview3d_is_not_a_valid_3d_output(self):
        d = copy.deepcopy(APP)
        pv = next(n for n in d["nodes"] if n["type"] == "Preview3DAdvanced")
        d["extra"]["linearData"]["outputs"] = [pv["id"]]
        self.assertTrue(problems(validate.check_app, "app", d))


class ModelMetadata(unittest.TestCase):
    def test_hash_mismatch_is_rejected(self):
        manifest = json.loads((ROOT / "data" / "models.json").read_text(encoding="utf-8"))
        d = copy.deepcopy(APP)
        for n in d["nodes"]:
            for m in n.get("properties", {}).get("models", []) or []:
                m["hash"] = "0" * 64
        self.assertTrue(any("disagrees" in e for e in problems(validate.check_models_in_graph, "app", d, manifest)))

    def test_clean(self):
        manifest = json.loads((ROOT / "data" / "models.json").read_text(encoding="utf-8"))
        self.assertEqual(problems(validate.check_models_in_graph, "app", APP, manifest), [])


class Hygiene(unittest.TestCase):
    def test_secrets_and_paths_are_found(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.md").write_text("token ghp_" + "A" * 36 + "\nsee C:\\Users\\jdoe\\secret", encoding="utf-8")
            old = validate.ROOT
            validate.ROOT = tmp
            try:
                msgs = problems(validate.check_hygiene, [tmp / "a.md"])
            finally:
                validate.ROOT = old
        self.assertTrue(any("GitHub token" in m for m in msgs))
        self.assertTrue(any("personal path" in m for m in msgs))

    def test_broken_markdown_link(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.md").write_text("[ok](a.md) [bad](missing.md) [web](https://example.org)", encoding="utf-8")
            old = validate.ROOT
            validate.ROOT = tmp
            try:
                msgs = problems(validate.check_links, [tmp / "a.md"])
            finally:
                validate.ROOT = old
        self.assertEqual(len(msgs), 1)
        self.assertIn("missing.md", msgs[0])


if __name__ == "__main__":
    unittest.main()
