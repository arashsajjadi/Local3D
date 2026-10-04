#!/usr/bin/env python3
"""Build the Local3D App Mode workflows from the official ComfyUI templates.

The official templates (vendored unchanged in ``workflows/upstream/``, MIT, Comfy-Org/workflow_templates) stay the
source of truth for every model-correctness detail. This script only *patches* them, deterministically:

* adds a few public controls (Model, Quality, Background, Seed) built from Comfy Core nodes only
* routes the quality presets (``data/presets.json``) through tiny Math Expression tables
* mutes diagnostic previews, marks the Save node + prepared-image preview as the app outputs
* writes ``extra.linearMode`` / ``extra.linearData`` so ComfyUI opens the file as an App

    python scripts/build_workflows.py          # rewrite local3d_pack/example_workflows/*.app.json
    python scripts/build_workflows.py --check  # exit 1 if the committed files are out of date
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "workflows" / "upstream"
OUT = ROOT / "local3d_pack"
PRESETS = ROOT / "data" / "presets.json"
VERSION = "0.1.0"
FRONTEND = "1.53.6"  # frontend pinned by the tested ComfyUI release (informational)


# --------------------------------------------------------------------------------------------------
# Minimal graph editor for ComfyUI "UI format" workflows (version 0.4)
# --------------------------------------------------------------------------------------------------
class Graph:
    def __init__(self, data: dict):
        self.d = copy.deepcopy(data)
        self.nodes = {n["id"]: n for n in self.d["nodes"]}
        self.links = {l[0]: l for l in self.d["links"]}
        self._nid = max(self.d.get("last_node_id", 0), max(self.nodes, default=0))
        self._lid = max(self.d.get("last_link_id", 0), max(self.links, default=0))

    # -- nodes ------------------------------------------------------------------------------------
    def add(self, type_, *, title=None, pos=(0, 0), size=(300, 110), widgets=None, inputs=None, outputs=None,
            props=None, mode=0, color=None, bgcolor=None) -> int:
        self._nid += 1
        node = {
            "id": self._nid, "type": type_, "pos": list(pos), "size": list(size), "flags": {},
            "order": self._nid, "mode": mode,
            "inputs": [dict(i, link=None) for i in (inputs or [])],
            "outputs": [dict(o, links=[]) for o in (outputs or [])],
            "properties": {"cnr_id": "comfy-core", "ver": "0.38.0", "Node name for S&R": type_, **(props or {})},
        }
        if title:
            node["title"] = title
        if widgets is not None:
            node["widgets_values"] = widgets
        if color:
            node["color"] = color
        if bgcolor:
            node["bgcolor"] = bgcolor
        self.d["nodes"].append(node)
        self.nodes[node["id"]] = node
        return node["id"]

    def remove(self, nid: int):
        node = self.nodes.pop(nid)
        self.d["nodes"].remove(node)
        for inp in node.get("inputs", []):
            if inp.get("link") is not None:
                self._drop_link(inp["link"])
        for out in node.get("outputs", []):
            for lid in list(out.get("links") or []):
                self._drop_link(lid)

    # -- links ------------------------------------------------------------------------------------
    def _drop_link(self, lid: int):
        l = self.links.pop(lid, None)
        if not l:
            return
        self.d["links"].remove(l)
        src = self.nodes.get(l[1])
        if src:
            links = src["outputs"][l[2]].get("links") or []
            if lid in links:
                links.remove(lid)
        dst = self.nodes.get(l[3])
        if dst and l[4] < len(dst.get("inputs", [])) and dst["inputs"][l[4]].get("link") == lid:
            dst["inputs"][l[4]]["link"] = None

    def out_slot(self, nid: int, name_or_slot) -> int:
        if isinstance(name_or_slot, int):
            return name_or_slot
        for i, o in enumerate(self.nodes[nid]["outputs"]):
            if o["name"] == name_or_slot:
                return i
        raise KeyError(f"node {nid} has no output {name_or_slot!r}")

    def connect(self, src: int, src_out, dst: int, dst_input: str, *, dtype=None, widget=False, label=None):
        """Link src output -> dst input, replacing any existing link. ``widget=True`` converts a widget to a socket."""
        node = self.nodes[dst]
        slot = next((i for i, x in enumerate(node["inputs"]) if x["name"] == dst_input), None)
        s = self.out_slot(src, src_out)
        typ = dtype or self.nodes[src]["outputs"][s]["type"]
        if slot is None:
            entry = {"name": dst_input, "type": typ, "link": None}
            if widget:
                entry["widget"] = {"name": dst_input}
            node["inputs"].append(entry)
            slot = len(node["inputs"]) - 1
        if label:
            node["inputs"][slot]["label"] = label
        if node["inputs"][slot].get("link") is not None:
            self._drop_link(node["inputs"][slot]["link"])
        self._lid += 1
        link = [self._lid, src, s, dst, slot, typ]
        self.d["links"].append(link)
        self.links[self._lid] = link
        self.nodes[src]["outputs"][s]["links"].append(self._lid)
        node["inputs"][slot]["link"] = self._lid
        return self._lid

    def label_widget(self, nid: int, widget: str, label: str, wtype: str):
        """Give a widget a socket entry (needed to carry a display label for App Mode)."""
        node = self.nodes[nid]
        for i in node["inputs"]:
            if i["name"] == widget:
                i["label"] = label
                return
        node["inputs"].append({"name": widget, "type": wtype, "widget": {"name": widget}, "label": label, "link": None})

    # -- decoration -------------------------------------------------------------------------------
    def group(self, title, x, y, w, h, color="#3f789e"):
        gid = max([g.get("id", 0) for g in self.d.setdefault("groups", [])] + [0]) + 1
        self.d["groups"].append({"id": gid, "title": title, "bounding": [x, y, w, h], "color": color,
                                 "font_size": 24, "flags": {}})

    def mute(self, *ids):
        for i in ids:
            self.nodes[i]["mode"] = 2

    def finish(self, name: str) -> dict:
        self.d["last_node_id"] = max(self.nodes)
        self.d["last_link_id"] = max(self.links) if self.links else 0
        self.d["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"local3d/{name}"))
        self.d["links"].sort(key=lambda l: l[0])
        self.d["nodes"].sort(key=lambda n: n["id"])
        return self.d


# --------------------------------------------------------------------------------------------------
# Node recipes (Comfy Core nodes only)
# --------------------------------------------------------------------------------------------------
def combo(g: Graph, title: str, label: str, options: list[str], default: str, pos, tip: str) -> int:
    return g.add(
        "CustomCombo", title=title, pos=pos, size=(330, 190),
        widgets=[default, options.index(default), *options, ""],
        inputs=[{"name": "choice", "type": "COMBO", "widget": {"name": "choice"}, "label": label, "localized_name": "choice"}],
        outputs=[{"name": "STRING", "type": "STRING", "localized_name": "STRING"},
                 {"name": "INDEX", "type": "INT", "localized_name": "INDEX"}],
        props={"Node name for S&R": "CustomCombo", "local3d_tip": tip},
    )


def math(g: Graph, title: str, expr: str, source: int, source_out, pos, extra_in: list[tuple] = ()) -> int:
    """Math Expression node. ``source`` feeds variable ``a``; ``extra_in`` = [(node, out, 'b'), ...]."""
    names = ["a"] + [n for _, _, n in extra_in]
    nid = g.add(
        "ComfyMathExpression", title=title, pos=pos, size=(360, 120), widgets=[expr],
        inputs=[{"label": n, "localized_name": f"values.{n}", "name": f"values.{n}", "type": "FLOAT,INT,BOOLEAN",
                 **({"shape": 7} if n != "a" else {})} for n in names],
        outputs=[{"localized_name": "FLOAT", "name": "FLOAT", "type": "FLOAT"},
                 {"localized_name": "INT", "name": "INT", "type": "INT"},
                 {"localized_name": "BOOL", "name": "BOOL", "type": "BOOLEAN"}],
    )
    g.connect(source, source_out, nid, "values.a", dtype="INT")
    for src, out, n in extra_in:
        g.connect(src, out, nid, f"values.{n}", dtype="INT")
    return nid


def table(values: list, key: str) -> str:
    """Fast / Balanced / Maximum lookup keyed by the Quality combo's INDEX output.

    ComfyUI's Math Expression node (simpleeval) has no list literals, so this is a conditional chain."""
    expr = str(values[-1])
    for i in range(len(values) - 2, -1, -1):
        expr = f"{values[i]} if a == {i} else ({expr})"
    return expr


def note(g: Graph, text: str, pos, size=(520, 320), title="Local3D") -> int:
    return g.add("MarkdownNote", title=title, pos=pos, size=size, widgets=[text],
                 props={"Node name for S&R": "MarkdownNote"}, color="#233", bgcolor="#355")


def app_meta(g: Graph, name: str, inputs: list, outputs: list):
    extra = g.d.setdefault("extra", {})
    extra["frontendVersion"] = FRONTEND
    extra["linearMode"] = True
    extra["linearData"] = {"inputs": inputs, "outputs": outputs}
    extra["local3d"] = {"app": name, "version": VERSION}
    for k in ("VHS_latentpreview", "VHS_latentpreviewrate", "VHS_MetadataImage", "VHS_KeepIntermediate"):
        extra.pop(k, None)


# --------------------------------------------------------------------------------------------------
# Image -> 3D app
# --------------------------------------------------------------------------------------------------
MODEL_OPTIONS = ["Auto — Recommended", "Pixal3D — Best match to reference", "TRELLIS.2 — Complex geometry & PBR"]
QUALITY_OPTIONS = ["Fast", "Balanced", "Maximum"]
BACKGROUND_OPTIONS = ["Auto", "Remove", "Keep"]


def load_presets() -> dict:
    return json.loads(PRESETS.read_text(encoding="utf-8"))


def _image_graph():
    """Patch the official template; returns (graph, ids) so the prompt app can reuse the 3D half."""
    P = load_presets()["parameters"]
    up = json.loads((UPSTREAM / "3d_pixal3d_trellis2_image_to_model.json").read_text(encoding="utf-8"))
    g = Graph(up)
    X, Y = -5100, -1560  # control strip, top-left of the official graph

    # ---- public controls -------------------------------------------------------------------------
    model = combo(g, "Model", "Model", MODEL_OPTIONS, MODEL_OPTIONS[0], (X, Y),
                  "Auto uses Pixal3D. Choose TRELLIS.2 for complex or thin geometry.")
    quality = combo(g, "Quality", "Quality", QUALITY_OPTIONS, "Balanced", (X + 360, Y),
                    "Fast = quick preview, Balanced = recommended, Maximum = most detail (needs the most GPU memory).")
    background = combo(g, "Background", "Background", BACKGROUND_OPTIONS, "Auto", (X + 720, Y),
                       "Auto removes the background. Keep uses your image's own transparency.")
    seed = g.add("PrimitiveInt", title="Seed", pos=(X + 1080, Y), size=(300, 110), widgets=[1234, "randomize"],
                 inputs=[{"name": "value", "type": "INT", "widget": {"name": "value"}, "label": "Seed", "localized_name": "value"}],
                 outputs=[{"name": "INT", "type": "INT", "localized_name": "INT"}])

    # ---- model switch: replaces the template's boolean ("true = TRELLIS.2") ---------------------------
    is_trellis = math(g, "Model is TRELLIS.2?", "a == 2", model, "INDEX", (X, Y + 240))
    for sw in (314, 315, 318):
        g.connect(is_trellis, "BOOL", sw, "switch", dtype="BOOLEAN", widget=True)
    g.remove(316)
    g.remove(317)  # markdown note that documented the removed boolean

    # ---- quality presets: one tiny table per parameter ------------------------------------------
    rows = [
        ("Preset: cascade resolution", "cascade_resolution", 94, "target_resolution"),
        ("Preset: remesh resolution", "remesh_resolution", 241, "resolution"),
        ("Preset: max faces", "max_faces", 186, "target_face_count"),
        ("Preset: texture size", "texture_size", None, None),
        ("Preset: normal map size", "normal_map_size", 224, "resolution"),
        ("Preset: AO map size", "ao_map_size", 233, "resolution"),
    ]
    tex_math = None
    for i, (title, key, nid, inp) in enumerate(rows):
        m = math(g, title, table(P[key], key), quality, "INDEX", (X + 400, Y + 240 + i * 150))
        if nid is not None:
            g.connect(m, "INT", nid, inp, dtype="INT", widget=True)
        else:
            tex_math = m
    # texture size replaces the template's single "Texture Resolution" primitive
    g.connect(tex_math, "INT", 196, "resolution", dtype="INT", widget=True)
    g.connect(tex_math, "INT", 147, "texture_size", dtype="INT", widget=True)
    g.remove(288)

    # ---- one seed for every sampler ---------------------------------------------------------------
    for ks in (3, 18, 23, 12):
        g.connect(seed, "INT", ks, "seed", dtype="INT", widget=True)

    # ---- background handling: Auto = AI matte x your cutout, Remove = AI matte, Keep = your cutout --
    inv = g.add("InvertMask", title="Your cutout (alpha)", pos=(X + 800, Y + 240), size=(260, 60),
                inputs=[{"name": "mask", "type": "MASK"}], outputs=[{"name": "MASK", "type": "MASK"}])
    g.connect(122, 1, inv, "mask")
    auto_mask = g.add(
        "MaskComposite", title="Auto: AI matte × your cutout", pos=(X + 800, Y + 360), size=(300, 160),
        widgets=[0, 0, "multiply"],
        inputs=[{"name": "destination", "type": "MASK"}, {"name": "source", "type": "MASK"}],
        outputs=[{"name": "MASK", "type": "MASK"}])
    g.connect(192, "mask", auto_mask, "destination")
    g.connect(inv, 0, auto_mask, "source")
    bg_is_remove = math(g, "Background is Remove?", "a == 1", background, "INDEX", (X + 800, Y + 600))
    bg_is_keep = math(g, "Background is Keep?", "a == 2", background, "INDEX", (X + 800, Y + 750))
    sw_remove = g.add(
        "ComfySwitchNode", title="Switch: Remove (AI matte only)", pos=(X + 1200, Y + 360), size=(300, 110), widgets=[False],
        inputs=[{"name": "on_false", "type": "MASK"}, {"name": "on_true", "type": "MASK"}],
        outputs=[{"name": "output", "type": "MASK"}])
    g.connect(auto_mask, 0, sw_remove, "on_false")
    g.connect(192, "mask", sw_remove, "on_true")
    g.connect(bg_is_remove, "BOOL", sw_remove, "switch", dtype="BOOLEAN", widget=True)
    # template node 248 becomes "Keep"
    g.nodes[248]["title"] = "Switch: Keep (your cutout)"
    g.connect(sw_remove, 0, 248, "on_false")
    g.connect(inv, 0, 248, "on_true")
    g.connect(bg_is_keep, "BOOL", 248, "switch", dtype="BOOLEAN", widget=True)
    g.nodes[248]["widgets_values"] = [False]
    g.nodes[248].pop("widgets_values_named", None)

    # ---- terminal diagnostics off by default (kept for people who open the graph) ------------------
    # NOTE: the template's PreviewImage nodes for base colour / metallic / roughness / normal / AO (164, 207, 208,
    # 226, 235) are pass-through nodes in the data path; muting them breaks the graph, so they stay active.
    g.mute(246, 323, 262, 261)

    # ---- outputs / naming ---------------------------------------------------------------------
    g.nodes[322]["widgets_values"][0] = "Local3D/model"
    g.nodes[302]["title"] = "Prepared image (what the model sees)"
    g.nodes[122]["widgets_values"][0] = "Local3D_example_owl.jpg"  # copied into the input folder on first run
    g.label_widget(122, "image", "Image", "COMBO")

    # ---- documentation inside the graph -----------------------------------------------------------
    note(g, "## Local3D — Image to 3D\n\nThis graph is the official **Pixal3D & TRELLIS.2** workflow with a few "
            "Comfy Core nodes added for the app controls (Model, Quality, Background, Seed). The quality presets live in "
            "the *Preset* Math Expression nodes (generated from `data/presets.json`).\n\n"
            "Diagnostic previews are muted; un-mute them to inspect stages. Upstream: Comfy-Org/workflow_templates (MIT).",
         (X, Y - 380), (760, 260))
    g.group("Local3D controls (public app inputs)", X - 40, Y - 80, 1460, 460, "#8A8")
    g.group("Quality presets (data/presets.json)", X + 360, Y + 200, 380, 960, "#a1309b")
    g.group("Background handling", X + 780, Y + 200, 740, 800, "#b58b2a")

    enrich_upstream_models(g)
    ids = {"model": model, "quality": quality, "background": background, "seed": seed, "bg_nodes": [inv, auto_mask, bg_is_remove, bg_is_keep, sw_remove]}
    return g, ids


def build_image_app() -> dict:
    g, ids = _image_graph()
    inputs = [  # descriptions stay under ~34 characters: App Mode shows them on a single line
        [122, "image", {"description": "Drop ONE object, fully in frame"}],
        [ids["model"], "choice", {"description": "Auto = Pixal3D (recommended)"}],
        [ids["quality"], "choice", {"description": "Balanced is the recommended mode"}],
        [ids["background"], "choice", {"description": "Auto removes it. Keep = cutout"}],
        [ids["seed"], "value", {"description": "Same seed = same result"}],
    ]
    app_meta(g, "image-to-3d", inputs, [322, 302])
    return g.finish("image-to-3d")


# --------------------------------------------------------------------------------------------------
# Prompt -> reference image stage (FLUX.2 klein 4B distilled; parameters copied from the official template)
# --------------------------------------------------------------------------------------------------
PROMPT_SUFFIX = (", a single complete object centered in the frame and fully visible with nothing cropped, "
                 "shown in a three-quarter front view from slightly above, soft even studio lighting, "
                 "plain seamless neutral grey background, clean unmarked surfaces, photorealistic 3D render")
DEFAULT_PROMPT = "A mechanical owl made of brass"
MANIFEST = ROOT / "data" / "models.json"
CANDIDATE_OPTIONS = ["1", "2", "4"]


def model_props(*file_ids: str) -> dict:
    """properties.models metadata (ComfyUI's own missing-model download UI reads this) from data/models.json."""
    files = {f["id"]: f for f in json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]}
    out = []
    for fid in file_ids:
        f = files[fid]
        out.append({"name": f["dest"].split("/")[-1], "directory": f["dest"].split("/")[0],
                    "url": f"https://huggingface.co/{f['repo']}/resolve/{f['revision']}/{f['path']}",
                    "hash": f["sha256"], "hash_type": "SHA256"})
    return {"models": out}


def enrich_upstream_models(g: Graph):
    """Add SHA-256 hashes (from data/models.json) to the model metadata the official template already embeds."""
    files = {f["dest"].split("/")[-1]: f for f in json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]}
    for n in g.nodes.values():
        for m in n.get("properties", {}).get("models", []) or []:
            f = files.get(m["name"])
            if f:
                m["hash"], m["hash_type"] = f["sha256"], "SHA256"


# FLUX.2 klein weight formats per GPU class (picked at launch from the GPU's compute capability)
KLEIN_VARIANTS = {"blackwell": ("klein-dit", "klein-te"), "ada": ("klein-dit-fp8", "klein-te-bf16"), "legacy": ("klein-dit-bf16", "klein-te-bf16")}


def klein_files(variant: str) -> tuple[str, str, str, str]:
    files = {f["id"]: f for f in json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]}
    dit_id, te_id = KLEIN_VARIANTS[variant]
    return dit_id, te_id, files[dit_id]["dest"].split("/")[-1], files[te_id]["dest"].split("/")[-1]


def add_reference_stage(g: Graph, prompt: int, friendly: int, seed: int, batch_src, origin, variant: str = "blackwell") -> int:
    """Add prompt framing + FLUX.2 klein 4B distilled text-to-image. Returns the VAEDecode node (IMAGE)."""
    x, y = origin
    dit_id, te_id, dit_name, te_name = klein_files(variant)
    S = {"type": "STRING"}
    concat = g.add("StringConcatenate", title="Add 3D-friendly framing", pos=(x, y), size=(340, 170),
                   widgets=["", PROMPT_SUFFIX, ""], outputs=[{"name": "STRING", **S}])
    g.connect(prompt, 0, concat, "string_a", dtype="STRING", widget=True)
    pick = g.add("ComfySwitchNode", title="Use 3D-friendly framing?", pos=(x + 380, y), size=(300, 110), widgets=[True],
                 inputs=[{"name": "on_false", **S}, {"name": "on_true", **S}], outputs=[{"name": "output", **S}])
    g.connect(prompt, 0, pick, "on_false")
    g.connect(concat, 0, pick, "on_true")
    g.connect(friendly, 0, pick, "switch", dtype="BOOLEAN", widget=True)

    unet = g.add("UNETLoader", title="FLUX.2 klein 4B (distilled)", pos=(x, y + 240), size=(340, 100),
                 widgets=[dit_name, "default"], outputs=[{"name": "MODEL", "type": "MODEL"}],
                 props=model_props(dit_id))
    clip = g.add("CLIPLoader", title="Qwen3 text encoder", pos=(x, y + 380), size=(340, 120),
                 widgets=[te_name, "flux2", "default"], outputs=[{"name": "CLIP", "type": "CLIP"}],
                 props=model_props(te_id))
    vae = g.add("VAELoader", title="FLUX.2 VAE", pos=(x, y + 540), size=(340, 80),
                widgets=["flux2-vae.safetensors"], outputs=[{"name": "VAE", "type": "VAE"}], props=model_props("klein-vae"))
    enc = g.add("CLIPTextEncode", title="Encode prompt", pos=(x + 380, y + 240), size=(340, 120), widgets=[""],
                inputs=[{"name": "clip", "type": "CLIP"}], outputs=[{"name": "CONDITIONING", "type": "CONDITIONING"}])
    g.connect(clip, 0, enc, "clip")
    g.connect(pick, 0, enc, "text", dtype="STRING", widget=True)
    zero = g.add("ConditioningZeroOut", pos=(x + 380, y + 400), size=(260, 60),
                 inputs=[{"name": "conditioning", "type": "CONDITIONING"}], outputs=[{"name": "CONDITIONING", "type": "CONDITIONING"}])
    g.connect(enc, 0, zero, "conditioning")
    guider = g.add("CFGGuider", pos=(x + 760, y + 240), size=(260, 120), widgets=[1],
                   inputs=[{"name": "model", "type": "MODEL"}, {"name": "positive", "type": "CONDITIONING"},
                           {"name": "negative", "type": "CONDITIONING"}], outputs=[{"name": "GUIDER", "type": "GUIDER"}])
    g.connect(unet, 0, guider, "model")
    g.connect(enc, 0, guider, "positive")
    g.connect(zero, 0, guider, "negative")
    sampler = g.add("KSamplerSelect", pos=(x + 760, y + 400), size=(260, 60), widgets=["euler"], outputs=[{"name": "SAMPLER", "type": "SAMPLER"}])
    sigmas = g.add("Flux2Scheduler", pos=(x + 760, y + 500), size=(260, 110), widgets=[4, 1024, 1024], outputs=[{"name": "SIGMAS", "type": "SIGMAS"}])
    noise = g.add("RandomNoise", pos=(x + 760, y + 650), size=(260, 110), widgets=[0, "fixed"], outputs=[{"name": "NOISE", "type": "NOISE"}])
    g.connect(seed, 0, noise, "noise_seed", dtype="INT", widget=True)
    latent = g.add("EmptyFlux2LatentImage", pos=(x + 760, y + 800), size=(260, 130), widgets=[1024, 1024, 1], outputs=[{"name": "LATENT", "type": "LATENT"}])
    if batch_src is not None:
        g.connect(batch_src, "INT", latent, "batch_size", dtype="INT", widget=True)
    sample = g.add("SamplerCustomAdvanced", pos=(x + 1080, y + 240), size=(260, 140),
                   inputs=[{"name": "noise", "type": "NOISE"}, {"name": "guider", "type": "GUIDER"}, {"name": "sampler", "type": "SAMPLER"},
                           {"name": "sigmas", "type": "SIGMAS"}, {"name": "latent_image", "type": "LATENT"}],
                   outputs=[{"name": "output", "type": "LATENT"}, {"name": "denoised_output", "type": "LATENT"}])
    for dst, src in (("noise", noise), ("guider", guider), ("sampler", sampler), ("sigmas", sigmas), ("latent_image", latent)):
        g.connect(src, 0, sample, dst)
    decode = g.add("VAEDecode", title="Reference image", pos=(x + 1080, y + 440), size=(260, 60),
                   inputs=[{"name": "samples", "type": "LATENT"}, {"name": "vae", "type": "VAE"}], outputs=[{"name": "IMAGE", "type": "IMAGE"}])
    g.connect(sample, 0, decode, "samples")
    g.connect(vae, 0, decode, "vae")
    g.group("Reference image (FLUX.2 klein 4B, 4 steps)", x - 40, y - 80, 1440, 1100, "#3f789e")
    return decode


def prompt_controls(g: Graph, origin):
    x, y = origin
    prompt = g.add("PrimitiveStringMultiline", title="Prompt", pos=(x, y), size=(380, 200), widgets=[DEFAULT_PROMPT],
                   inputs=[{"name": "value", "type": "STRING", "widget": {"name": "value"}, "label": "Prompt", "localized_name": "value"}],
                   outputs=[{"name": "STRING", "type": "STRING"}])
    friendly = g.add("PrimitiveBoolean", title="3D-friendly reference", pos=(x + 420, y), size=(330, 90), widgets=[True],
                     inputs=[{"name": "value", "type": "BOOLEAN", "widget": {"name": "value"}, "label": "3D-friendly reference", "localized_name": "value"}],
                     outputs=[{"name": "BOOLEAN", "type": "BOOLEAN"}])
    return prompt, friendly


def build_prompt_app(variant: str = "blackwell") -> dict:
    g, ids = _image_graph()
    # the picture comes from the prompt, so the image-specific parts go away
    for nid in ids["bg_nodes"] + [248, ids["background"], 122]:
        g.remove(nid)
    g.connect(192, "mask", 303, "mask")  # BiRefNet matte straight into the crop step
    X, Y = -5100, -1560
    prompt, friendly = prompt_controls(g, (X + 720, Y))
    decode = add_reference_stage(g, prompt, friendly, ids["seed"], None, (X - 1900, Y + 640), variant)
    g.connect(decode, 0, 192, "image")
    g.connect(decode, 0, 312, "images")
    ref = g.add("SaveImage", title="Reference image (saved)", pos=(X - 450, Y + 640), size=(320, 280),
                widgets=["Local3D_reference"], inputs=[{"name": "images", "type": "IMAGE"}], outputs=[{"name": "images", "type": "IMAGE"}])
    g.connect(decode, 0, ref, "images")
    g.nodes[322]["widgets_values"][0] = "models/prompt"
    inputs = [
        [prompt, "value", {"description": "Describe ONE object"}],
        [friendly, "value", {"description": "Adds framing that helps 3D"}],
        [ids["model"], "choice", {"description": "Auto = Pixal3D (recommended)"}],
        [ids["quality"], "choice", {"description": "Balanced is the recommended mode"}],
        [ids["seed"], "value", {"description": "Same seed = same result"}],
    ]
    note(g, "## Local3D — Prompt to 3D\n\nPrompt → reference image (FLUX.2 klein 4B) → 3D model. "
            "The reference image is saved as `Local3D_reference_*.png` so you can reuse it in *Image to 3D*.",
         (X, Y - 380), (760, 200))
    app_meta(g, "prompt-to-3d", inputs, [ref, 322])
    return g.finish("prompt-to-3d/" + variant)


def build_reference_app(variant: str = "blackwell") -> dict:
    g = Graph({"nodes": [], "links": [], "groups": [], "config": {}, "extra": {}, "version": 0.4,
               "last_node_id": 0, "last_link_id": 0, "revision": 0})
    X, Y = 0, 0
    prompt, friendly = prompt_controls(g, (X, Y))
    seed = g.add("PrimitiveInt", title="Seed", pos=(X + 800, Y), size=(300, 110), widgets=[1234, "randomize"],
                 inputs=[{"name": "value", "type": "INT", "widget": {"name": "value"}, "label": "Seed", "localized_name": "value"}],
                 outputs=[{"name": "INT", "type": "INT"}])
    cands = combo(g, "Pictures", "Pictures", CANDIDATE_OPTIONS, "4", (X + 1140, Y), "How many reference pictures to make.")
    batch = math(g, "Pictures to make", "1 if a == 0 else (2 if a == 1 else 4)", cands, "INDEX", (X + 1140, Y + 240))
    decode = add_reference_stage(g, prompt, friendly, seed, batch, (X, Y + 300), variant)
    out = g.add("SaveImage", title="Reference pictures", pos=(X + 1480, Y + 540), size=(320, 280),
                widgets=["Local3D_reference"], inputs=[{"name": "images", "type": "IMAGE"}], outputs=[{"name": "images", "type": "IMAGE"}])
    g.connect(decode, 0, out, "images")
    note(g, "## Local3D — Reference pictures\n\nMake a few reference pictures from a prompt, pick the best one, then open "
            "**Image to 3D** and choose it there. Pictures are saved as `Local3D_reference_*.png`.", (X, Y - 330), (700, 200))
    inputs = [
        [prompt, "value", {"description": "Describe ONE object"}],
        [friendly, "value", {"description": "Adds framing that helps 3D"}],
        [cands, "choice", {"description": "How many pictures to make"}],
        [seed, "value", {"description": "Same seed = same pictures"}],
    ]
    app_meta(g, "reference-pictures", inputs, [out])
    return g.finish("reference-pictures/" + variant)


APPS = {  # path relative to local3d_pack/  ->  builder
    "example_workflows/Local3D_Image_to_3D.app.json": build_image_app,
    "example_workflows/Local3D_Prompt_to_3D.app.json": lambda: build_prompt_app("blackwell"),
    "example_workflows/Local3D_Reference_Pictures.app.json": lambda: build_reference_app("blackwell"),
}
for _v in ("ada", "legacy"):  # same apps with the weight formats that GPU class can run; the launcher copies these over
    APPS[f"variants/{_v}/Local3D_Prompt_to_3D.app.json"] = (lambda v=_v: build_prompt_app(v))
    APPS[f"variants/{_v}/Local3D_Reference_Pictures.app.json"] = (lambda v=_v: build_reference_app(v))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    stale = []
    for name, fn in APPS.items():
        text = json.dumps(fn(), indent=1, ensure_ascii=False) + "\n"
        path = OUT / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print("wrote", path.relative_to(ROOT))
    if stale:
        print("out of date:", ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
