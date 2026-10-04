"""Preset tables, graph-editing invariants and the model provisioning logic."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_workflows as bw  # noqa: E402
import provision_models as pm  # noqa: E402

PRESETS = json.loads((ROOT / "data" / "presets.json").read_text(encoding="utf-8"))


class PresetTables(unittest.TestCase):
    def test_table_expression_returns_each_level(self):
        for key, values in PRESETS["parameters"].items():
            expr = bw.table(values, key)
            for i, want in enumerate(values):
                self.assertEqual(eval(expr, {"__builtins__": {}}, {"a": i}), want, key)  # noqa: S307 - trusted literal

    def test_table_uses_only_what_comfys_math_node_allows(self):
        # simpleeval in ComfyUI has no list literals, so tables must be conditional chains
        expr = bw.table([1, 2, 3], "x")
        self.assertNotIn("[", expr)
        self.assertIn("if a ==", expr)

    def test_apps_embed_exactly_the_preset_values(self):
        d = bw.build_image_app()
        exprs = [n["widgets_values"][0] for n in d["nodes"] if n["type"] == "ComfyMathExpression"]
        for key, values in PRESETS["parameters"].items():
            self.assertIn(bw.table(values, key), exprs, key)

    def test_apps_are_deterministic(self):
        a = json.dumps(bw.build_prompt_app(), sort_keys=True)
        b = json.dumps(bw.build_prompt_app(), sort_keys=True)
        self.assertEqual(a, b)


class GraphEditing(unittest.TestCase):
    def setUp(self):
        self.g = bw.Graph({"nodes": [], "links": [], "groups": [], "extra": {}, "version": 0.4, "last_node_id": 0, "last_link_id": 0})
        self.a = self.g.add("PrimitiveInt", outputs=[{"name": "INT", "type": "INT"}], widgets=[1, "fixed"])
        self.b = self.g.add("PrimitiveInt", outputs=[{"name": "INT", "type": "INT"}], widgets=[2, "fixed"])
        self.c = self.g.add("ComfyMathExpression", inputs=[{"name": "values.a", "type": "INT"}], outputs=[{"name": "INT", "type": "INT"}], widgets=["a"])

    def consistent(self):
        for l in self.g.d["links"]:
            lid, s, ss, t, ts, _ = l
            self.assertIn(lid, self.g.nodes[s]["outputs"][ss]["links"])
            self.assertEqual(self.g.nodes[t]["inputs"][ts]["link"], lid)

    def test_connect_replaces_previous_link(self):
        self.g.connect(self.a, 0, self.c, "values.a")
        self.g.connect(self.b, 0, self.c, "values.a")
        self.assertEqual(len(self.g.d["links"]), 1)
        self.assertEqual(self.g.nodes[self.a]["outputs"][0]["links"], [])
        self.consistent()

    def test_remove_cleans_both_ends(self):
        self.g.connect(self.a, 0, self.c, "values.a")
        self.g.remove(self.a)
        self.assertEqual(self.g.d["links"], [])
        self.assertIsNone(self.g.nodes[self.c]["inputs"][0]["link"])

    def test_widget_can_become_socket(self):
        self.g.connect(self.a, 0, self.c, "extra_widget", dtype="INT", widget=True)
        entry = next(i for i in self.g.nodes[self.c]["inputs"] if i["name"] == "extra_widget")
        self.assertEqual(entry["widget"], {"name": "extra_widget"})
        self.consistent()

    def test_remove_never_follows_a_stale_link_id(self):
        self.g.connect(self.a, 0, self.c, "values.a")
        self.g.remove(self.c)
        self.assertEqual(self.g.nodes[self.a]["outputs"][0]["links"], [])


class Provisioning(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.f = {"id": "x", "pack": "core", "label": "X", "repo": "a/b", "revision": "0" * 40, "path": "vae/x.safetensors",
                  "dest": "vae/x.safetensors", "size": 11, "sha256": pm.hashlib.sha256(b"hello world").hexdigest()}

    def test_missing_unverified_ok(self):
        cache = pm.VerifyCache(self.tmp)
        self.assertEqual(pm.status_of(self.f, self.tmp, cache), "missing")
        dest = self.tmp / "vae" / "x.safetensors"
        dest.parent.mkdir()
        dest.write_bytes(b"hello world")
        self.assertEqual(pm.status_of(self.f, self.tmp, cache), "unverified")
        cache.remember(self.f, dest)
        self.assertEqual(pm.status_of(self.f, self.tmp, pm.VerifyCache(self.tmp)), "ok")

    def test_modified_file_is_no_longer_trusted(self):
        dest = self.tmp / "vae" / "x.safetensors"
        dest.parent.mkdir()
        dest.write_bytes(b"hello world")
        cache = pm.VerifyCache(self.tmp)
        cache.remember(self.f, dest)
        dest.write_bytes(b"HELLO WORLD")  # same size, different content and mtime
        self.assertNotEqual(pm.status_of(self.f, self.tmp, pm.VerifyCache(self.tmp)), "ok")

    def test_pack_selection(self):
        manifest = json.loads((ROOT / "data" / "models.json").read_text(encoding="utf-8"))
        core = pm.select_files(manifest, ["core"], [])
        both = pm.select_files(manifest, ["core", "prompt"], [])
        self.assertTrue(core and len(both) > len(core))
        self.assertEqual([f["id"] for f in pm.select_files(manifest, ["core"], ["birefnet"])], ["birefnet"])

    def test_gpu_classes_pick_exactly_one_of_each_klein_part(self):
        manifest = json.loads((ROOT / "data" / "models.json").read_text(encoding="utf-8"))
        for gpu in ("blackwell", "ada", "legacy"):
            files = pm.select_files(manifest, ["prompt"], [], gpu)
            for kind in ("diffusion_models/", "text_encoders/", "vae/"):
                self.assertEqual(sum(f["dest"].startswith(kind) for f in files), 1, (gpu, kind))
        # RTX 50-series gets the small nvfp4 build, older cards never get it
        self.assertIn("klein-dit", [f["id"] for f in pm.select_files(manifest, ["prompt"], [], "blackwell")])
        self.assertNotIn("klein-dit", [f["id"] for f in pm.select_files(manifest, ["prompt"], [], "legacy")])

    def test_prompt_app_variants_load_the_matching_weights(self):
        manifest = {f["id"]: f for f in json.loads((ROOT / "data" / "models.json").read_text(encoding="utf-8"))["files"]}
        for variant, (dit, te) in bw.KLEIN_VARIANTS.items():
            d = bw.build_prompt_app(variant)
            unets = [n["widgets_values"][0] for n in d["nodes"] if n["type"] == "UNETLoader" and "klein" in n["widgets_values"][0]]
            clips = [n["widgets_values"][0] for n in d["nodes"] if n["type"] == "CLIPLoader"]
            self.assertEqual(unets, [manifest[dit]["dest"].split("/")[-1]])
            self.assertEqual(clips, [manifest[te]["dest"].split("/")[-1]])

    def test_disk_preflight_refuses_when_full(self):
        big = dict(self.f, size=10 ** 18)
        with self.assertRaises(pm.Failure) as cm:
            pm.preflight_disk([big], self.tmp, pm.VerifyCache(self.tmp))
        self.assertEqual(cm.exception.code, pm.EXIT_DISK)

    def test_sha256_helper(self):
        p = self.tmp / "h.bin"
        p.write_bytes(b"hello world")
        self.assertEqual(pm.sha256_file(p), self.f["sha256"])


if __name__ == "__main__":
    unittest.main()
