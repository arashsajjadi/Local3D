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
VERSION = "0.1.2"
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


def math(g: Graph, title: str, expr: str, source: int, source_out, pos, extra_in: list[tuple] = (), source_dtype: str = "INT") -> int:
    """Math Expression node. ``source`` feeds variable ``a``; ``extra_in`` = [(node, out, 'b'[, dtype]), ...]."""
    names = ["a"] + [t[2] for t in extra_in]
    nid = g.add(
        "ComfyMathExpression", title=title, pos=pos, size=(360, 120), widgets=[expr],
        inputs=[{"label": n, "localized_name": f"values.{n}", "name": f"values.{n}", "type": "FLOAT,INT,BOOLEAN",
                 **({"shape": 7} if n != "a" else {})} for n in names],
        outputs=[{"localized_name": "FLOAT", "name": "FLOAT", "type": "FLOAT"},
                 {"localized_name": "INT", "name": "INT", "type": "INT"},
                 {"localized_name": "BOOL", "name": "BOOL", "type": "BOOLEAN"}],
    )
    g.connect(source, source_out, nid, "values.a", dtype=source_dtype)
    for t in extra_in:
        g.connect(t[0], t[1], nid, f"values.{t[2]}", dtype=t[3] if len(t) > 3 else "INT")
    return nid


def table(values: list, key: str) -> str:
    """Fast / Balanced / Maximum lookup keyed by the Quality combo's INDEX output.

    ComfyUI's Math Expression node (simpleeval) has no list literals, so this is a conditional chain."""
    expr = str(values[-1])
    for i in range(len(values) - 2, -1, -1):
        expr = f"{values[i]} if a == {i} else ({expr})"
    return expr


def table_capped(values: list, cap: int) -> str:
    """Quality table, lowered by the Output intent (b == 1 means "Game asset"); a cap never raises a value."""
    return f"min({table(values, '')}, {cap} if b == 1 else 1000000000)"


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
QUALITY_OPTIONS = ["Fast — quick preview", "Balanced — recommended", "Maximum — most detail, 16 GB GPU"]
INTENT_OPTIONS = ["High fidelity — keep all detail", "Game asset — about 30k triangles"]
BACKGROUND_OPTIONS = ["Auto — recommended", "Remove — AI cutout only", "Keep — my transparent PNG"]
SUBJECT_OPTIONS = ["Auto — recommended", "Object — products, toys, figurines", "Character bust — people", "Complex — thin or open shapes"]


def load_presets() -> dict:
    return json.loads(PRESETS.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------
# Subject routing: what kind of 3D problem is this picture? (docs/CHARACTER_ROUTING_DECISION.md)
# --------------------------------------------------------------------------------------------------
def _lit(g: Graph, text: str, pos, title="text") -> int:
    return g.add("PrimitiveString", title=title, pos=pos, size=(300, 60), widgets=[text],
                 inputs=[{"name": "value", "type": "STRING", "widget": {"name": "value"}}], outputs=[{"name": "STRING", "type": "STRING"}])


def _switch(g: Graph, title: str, cond, cond_out, on_false, on_true, pos, dtype="STRING") -> int:
    nid = g.add("ComfySwitchNode", title=title, pos=pos, size=(280, 100), widgets=[False],
                inputs=[{"name": "on_false", "type": dtype, "shape": 7}, {"name": "on_true", "type": dtype, "shape": 7}],
                outputs=[{"name": "output", "type": dtype}])
    g.connect(on_false, 0, nid, "on_false")
    g.connect(on_true, 0, nid, "on_true")
    g.connect(cond, cond_out, nid, "switch", dtype="BOOLEAN", widget=True)
    return nid


def _first_number(g: Graph, json_node: int, key: str, pos) -> int:
    """Number stored under ``key`` in the first JSON object of a text (the sentinel object guarantees there is one)."""
    ex = g.add("JsonExtractString", title=f"Read '{key}'", pos=pos, size=(300, 100), widgets=["", key], outputs=[{"name": "STRING", "type": "STRING"}])
    g.connect(json_node, 0, ex, "json_string", dtype="STRING", widget=True)
    num = g.add("ComfyNumberConvert", title=f"'{key}' as a number", pos=(pos[0] + 320, pos[1]), size=(220, 60),
                inputs=[{"name": "value", "type": "INT,FLOAT,STRING,BOOLEAN"}],
                outputs=[{"name": "FLOAT", "type": "FLOAT"}, {"name": "INT", "type": "INT"}])
    g.connect(ex, 0, num, "value", dtype="STRING")
    return num


def add_subject_routing(g: Graph, subject_combo: int, origin) -> dict:
    """Detect a person / face on the ORIGINAL picture, resolve the Subject control (Auto picks Character bust when a face is
    found), crop picture and mask to a bust when that is what the picture shows, and write a plain-language report.

    Detectors are Comfy Core nodes (RT-DETR person, MediaPipe face); a missing detection never fails the run: a sentinel JSON
    object makes the numbers fall back to -1 / 0, which the Math tables read as "nothing found"."""
    R = load_presets()["routing"]
    x, y = origin
    SENTINEL = '{"y": -1, "width": -1, "height": -1, "score": 0}'

    # ---- detectors -----------------------------------------------------------------------------------------------
    rt_model = g.add("UNETLoader", title="Person detector (RT-DETR)", pos=(x, y), size=(340, 100),
                     widgets=["rt_detr_v4-x-hgnet_fp16.safetensors", "default"], outputs=[{"name": "MODEL", "type": "MODEL"}],
                     props=model_props("rtdetr"))
    rt = g.add("RTDETR_detect", title="Find the person", pos=(x + 380, y), size=(340, 130), widgets=[0.3, "person", 1],
               outputs=[{"name": "bboxes", "type": "BOUNDING_BOX"}])
    g.connect(rt_model, 0, rt, "model")
    g.connect(122, 0, rt, "image")
    mp_model = g.add("LoadMediaPipeFaceLandmarker", title="Face detector (MediaPipe)", pos=(x, y + 160), size=(340, 70),
                     widgets=["mediapipe_face_fp32.safetensors"], outputs=[{"name": "FACE_DETECTION_MODEL", "type": "FACE_DETECTION_MODEL"}],
                     props=model_props("mediapipe-face"))
    mp = g.add("MediaPipeFaceLandmarker", title="Find the face", pos=(x + 380, y + 160), size=(340, 160), widgets=["both", 1, 0.3, "empty"],
               outputs=[{"name": "face_landmarks", "type": "FACE_LANDMARKS"}, {"name": "bboxes", "type": "BOUNDING_BOX"}])
    g.connect(mp_model, 0, mp, "face_detection_model")
    g.connect(122, 0, mp, "image")

    def as_json(src, out, row):
        cast = g.add("GetItemFromList", title="(any type)", pos=(x + 760, y + row), size=(200, 60), widgets=[0],
                     outputs=[{"name": "*", "type": "*"}])
        g.connect(src, out, cast, "list")
        text = g.add("ConvertArrayToString", title="Detections as text", pos=(x + 980, y + row), size=(240, 60), widgets=[0],
                     outputs=[{"name": "STRING", "type": "STRING"}])
        g.connect(cast, 0, text, "array", dtype="ARRAY")
        both = g.add("StringConcatenate", title="+ 'nothing found' fallback", pos=(x + 1240, y + row), size=(300, 160),
                     widgets=["", SENTINEL, " "], outputs=[{"name": "STRING", "type": "STRING"}])
        g.connect(text, 0, both, "string_a", dtype="STRING", widget=True)
        return both

    person_json = as_json(rt, 0, 0)
    face_json = as_json(mp, 1, 220)
    person_score = _first_number(g, person_json, "score", (x + 1580, y))
    face_score = _first_number(g, face_json, "score", (x + 1580, y + 140))
    face_y = _first_number(g, face_json, "y", (x + 1580, y + 280))
    face_h = _first_number(g, face_json, "height", (x + 1580, y + 420))
    person_y = _first_number(g, person_json, "y", (x + 1580, y + 560))
    person_h = _first_number(g, person_json, "height", (x + 1580, y + 700))
    person_w = _first_number(g, person_json, "width", (x + 1580, y + 840))

    # ---- decision -------------------------------------------------------------------------------------------------
    # subject codes: 0 Object, 1 Character bust, 2 Complex shapes.  Control index: 0 Auto, 1 Object, 2 Character, 3 Complex.
    img_size = g.add("GetImageSize", title="Picture size", pos=(x, y + 700), size=(200, 80),
                     outputs=[{"name": "width", "type": "INT"}, {"name": "height", "type": "INT"}, {"name": "batch_size", "type": "INT"}])
    g.connect(122, 0, img_size, "image")
    # Auto: a face that is big enough for a bust, AND (a person, or a face so large that this is a close portrait). A face without a
    # person is a toy, doll or statue; a small face means a full-length figure. Both stay Object (with a note).
    m_auto = math(g, "Auto: is it a person?",
                  f"1 if (a >= {R['face_score_min']} and c >= {R['bust_min_face_fraction']} * d and "
                  f"(b >= {R['person_score_min']} or c >= {R['portrait_face_fraction']} * d)) else 0",
                  face_score, 0, (x, y + 520), extra_in=[(person_score, 0, "b", "FLOAT"), (face_h, 0, "c", "FLOAT"), (img_size, "height", "d")],
                  source_dtype="FLOAT")
    m_subject = math(g, "Subject (resolved)", "1 if a == 2 else (0 if a == 1 else (2 if a == 3 else b))", subject_combo, "INDEX",
                     (x + 400, y + 520), extra_in=[(m_auto, "INT", "b")])
    # Does cutting make the subject bigger for the model? The 3D model sees a SQUARE crop of the subject's box, so only the longer side
    # counts: cutting a tall picture shrinks it (the officer: 1.6 times), cutting a square one changes nothing (1.0) and only costs
    # time, memory and context. a = face top, b = face height, c = person top, d = person height, e = person width.
    cut_line = f"a + {R['bust_cut_face_heights']} * b"
    m_gain = math(g, "Bust cut makes the subject larger for the model?",
                  f"1 if max(e, d) >= {R['bust_min_gain']} * max(e, {cut_line} - c) else 0", face_y, 0, (x + 800, y + 520),
                  extra_in=[(face_h, 0, "b", "FLOAT"), (person_y, 0, "c", "FLOAT"), (person_h, 0, "d", "FLOAT"), (person_w, 0, "e", "FLOAT")],
                  source_dtype="FLOAT")
    # The cut needs a face box and a cut line above the bottom edge. Under Auto it also has to pay; an explicit "Character bust" is the
    # user's call. a = face top, b = face height, c = picture height, d = subject, e = Subject control (0 = Auto), f = does cutting pay?
    cut_expr = (f"c if (d != 1 or b <= 0 or {cut_line} >= {R['bust_cut_max_fraction']} * c or (e == 0 and f == 0)) "
                f"else int({cut_line})")
    m_cut = math(g, "Bust cut: last picture row kept", cut_expr, face_y, 0, (x + 400, y + 700),
                 extra_in=[(face_h, 0, "b", "FLOAT"), (img_size, "height", "c"), (m_subject, "INT", "d"), (subject_combo, "INDEX", "e"), (m_gain, "INT", "f")],
                 source_dtype="FLOAT")

    # ---- crop the picture and the cutout to the bust ----------------------------------------------------------------
    box = g.add("PrimitiveBoundingBox", title="Bust box", pos=(x + 800, y + 700), size=(270, 130), widgets=[0, 0, 512, 512],
                outputs=[{"name": "BOUNDING_BOX", "type": "BOUNDING_BOX"}])
    g.connect(img_size, "width", box, "width", dtype="INT", widget=True)
    g.connect(m_cut, "INT", box, "height", dtype="INT", widget=True)
    crop_img = g.add("ImageCropV2", title="Crop picture to the bust", pos=(x + 1120, y + 700), size=(300, 120),
                     widgets=[{"x": 0, "y": 0, "width": 512, "height": 512}, 0, 0, 512, 512], outputs=[{"name": "IMAGE", "type": "IMAGE"}])
    g.connect(122, 0, crop_img, "image")
    g.connect(box, 0, crop_img, "crop_region", dtype="BOUNDING_BOX", widget=True)
    crop_alpha = g.add("CropMask", title="Crop your cutout to the bust", pos=(x + 1120, y + 860), size=(270, 130), widgets=[0, 0, 512, 512],
                       outputs=[{"name": "MASK", "type": "MASK"}])
    g.connect(122, 1, crop_alpha, "mask")
    g.connect(img_size, "width", crop_alpha, "width", dtype="INT", widget=True)
    g.connect(m_cut, "INT", crop_alpha, "height", dtype="INT", widget=True)

    # ---- plain-language report (an app output) ---------------------------------------------------------------------
    ry = y + 1120
    is_char = math(g, "Subject is Character bust?", "a == 1", m_subject, "INT", (x, ry))
    is_complex = math(g, "Subject is Complex?", "a == 2", m_subject, "INT", (x, ry + 150))
    is_auto = math(g, "Subject control is Auto?", "a == 0", subject_combo, "INDEX", (x, ry + 300))
    is_cropped = math(g, "Bust cut applied?", "a < b", m_cut, "INT", (x, ry + 450), extra_in=[(img_size, "height", "b")])
    # only under Auto: 1 = a person without a large, clear face (hidden, small or stylised), 2 = a face without a person (toy, doll, statue)
    unsure_code = math(g, "Unsure about the subject? (Auto only)",
                       f"0 if c != 0 else (1 if (a >= {R['person_score_min']} and (b < {R['face_score_min']} or d < {R['bust_min_face_fraction']} * e)) else "
                       f"(2 if (b >= {R['face_score_min']} and a < {R['person_score_min']} and d < {R['portrait_face_fraction']} * e) else 0))",
                       person_score, 0, (x, ry + 600),
                       extra_in=[(face_score, 0, "b", "FLOAT"), (subject_combo, "INDEX", "c"), (face_h, 0, "d", "FLOAT"), (img_size, "height", "e")],
                       source_dtype="FLOAT")
    unsure_person = math(g, "Unsure: person without a clear face?", "a == 1", unsure_code, "INT", (x, ry + 750))
    unsure_toy = math(g, "Unsure: face without a person?", "a == 2", unsure_code, "INT", (x, ry + 900))
    t_obj = _lit(g, "Object", (x + 400, ry), "Object")
    t_cplx = _lit(g, "Complex shapes (TRELLIS.2)", (x + 400, ry + 80), "Complex")
    t_char = _lit(g, "Character bust", (x + 400, ry + 160), "Character bust")
    name1 = _switch(g, "Name (complex?)", is_complex, "BOOL", t_obj, t_cplx, (x + 760, ry))
    name = _switch(g, "Name", is_char, "BOOL", name1, t_char, (x + 1080, ry))
    t_auto = _lit(g, "Auto picked it", (x + 400, ry + 260), "Auto")
    t_you = _lit(g, "your choice", (x + 400, ry + 340), "Chosen")
    how = _switch(g, "How", is_auto, "BOOL", t_you, t_auto, (x + 760, ry + 260))
    evidence = g.add("StringFormat", title="What it looked for", pos=(x + 400, ry + 440), size=(420, 140),
                     widgets=["Looked for: a face (score {a:.2f}) and a person (score {b:.2f}); scores run from 0 to 1."],
                     outputs=[{"name": "STRING", "type": "STRING"}])
    g.connect(face_score, 0, evidence, "values.a", dtype="FLOAT")
    g.connect(person_score, 0, evidence, "values.b", dtype="FLOAT")
    t_whole = _lit(g, "Framing: the whole picture", (x + 860, ry + 440), "Whole picture")
    framing_cut = g.add("StringFormat", title="Framing text", pos=(x + 860, ry + 520), size=(420, 130),
                        widgets=["Framing: cut below the chest, rows 0 to {a} of {b} kept, so the face and hands get more detail."],
                        outputs=[{"name": "STRING", "type": "STRING"}])
    g.connect(m_cut, "INT", framing_cut, "values.a", dtype="INT")
    g.connect(img_size, "height", framing_cut, "values.b", dtype="INT")
    t_whole_char = _lit(g, "Framing: the whole picture (cutting below the chest would not make the subject larger for the model, so it is used as it is)",
                        (x + 400, ry + 600), "Whole picture (character)")
    whole = _switch(g, "Whole picture text", is_char, "BOOL", t_whole, t_whole_char, (x + 1080, ry + 600))
    framing = _switch(g, "Framing", is_cropped, "BOOL", whole, framing_cut, (x + 1320, ry + 440))
    t_none = _lit(g, "", (x + 860, ry + 700), "(nothing)")
    t_hidden = _lit(g, "Hidden surfaces (the back and the far side) are inferred, not measured.", (x + 860, ry + 780), "Hidden surfaces")
    t_unsure = _lit(g, "Not sure: a person, but no large clear face (it may be hidden, small or stylised). Auto used the Object workflow; choose Character bust to crop to the upper body.",
                    (x + 860, ry + 860), "Unsure: person")
    t_toy = _lit(g, "Note: a face but no person, so this may be a toy, doll or statue. Auto kept the whole figure (Object workflow); choose Character bust to crop to the upper body.",
                 (x + 860, ry + 940), "Unsure: toy")
    note_unsure1 = _switch(g, "Note (person without a face?)", unsure_person, "BOOL", t_none, t_unsure, (x + 1320, ry + 780))
    note_unsure = _switch(g, "Note (face without a person?)", unsure_toy, "BOOL", note_unsure1, t_toy, (x + 1320, ry + 900))
    note_text = _switch(g, "Note", is_char, "BOOL", note_unsure, t_hidden, (x + 1620, ry + 780))
    report = g.add("StringFormat", title="Subject report", pos=(x + 1620, ry), size=(520, 300),
                   widgets=["Subject: {a} ({b})\n{c}\n{d}\n{e}"], outputs=[{"name": "STRING", "type": "STRING"}])
    for name_, src_ in (("a", name), ("b", how), ("c", evidence), ("d", framing), ("e", note_text)):
        g.connect(src_, 0, report, f"values.{name_}", dtype="STRING")
    shown = g.add("PreviewAny", title="Subject report (what Local3D decided and why)", pos=(x + 2180, ry), size=(420, 200),
                  inputs=[{"name": "source", "type": "*"}], outputs=[{"name": "STRING", "type": "STRING"}])
    g.connect(report, 0, shown, "source", dtype="STRING")

    g.group("Subject detection, bust framing and report (Local3D)", x - 40, y - 80, 2700, 2000, "#2a7f62")
    describe_stages(g, {rt_model: "Looking at your picture", mp_model: "Looking at your picture", rt: "Looking at your picture",
                        mp: "Looking at your picture", crop_img: "Framing the subject", shown: "Writing the report"})
    return {"subject": m_subject, "crop_img": crop_img, "crop_alpha": crop_alpha, "report": shown, "nodes_end": shown}


# App Mode shows node.properties["Execution Message"] while that node runs: real stages, not a fake progress bar
IMAGE_STAGES = {
    122: "Preparing your picture", 192: "Removing background", 312: "Preparing your picture",
    56: "Estimating the camera", 298: "Reading your picture", 299: "Reading your picture",
    118: "Loading models", 15: "Loading models", 117: "Loading models", 55: "Loading models", 193: "Loading models",
    40: "Loading models", 319: "Loading models",
    3: "Generating coarse geometry", 119: "Generating coarse geometry", 87: "Generating coarse geometry",
    91: "Refining geometry", 18: "Refining geometry", 94: "Refining geometry", 23: "Refining geometry", 92: "Refining geometry",
    98: "Generating materials", 12: "Generating materials", 93: "Generating materials",
    202: "Cleaning up the mesh", 241: "Cleaning up the mesh", 186: "Simplifying the mesh", 238: "Processing the mesh",
    196: "Unwrapping textures", 147: "Baking colour textures", 224: "Baking surface detail", 233: "Baking shading",
    210: "Packing the model", 260: "Packing the model", 285: "Packing the model", 322: "Saving the model",
}


def describe_stages(g: Graph, stages: dict):
    for nid, msg in stages.items():
        if nid in g.nodes:
            g.nodes[nid].setdefault("properties", {})["Execution Message"] = msg


def apply_quality(g: Graph, quality: int, output: int, seed: int, origin) -> None:
    """Wire the Fast / Balanced / Maximum tables (data/presets.json) and the Output intent into the 3D half that the Pixal3D
    templates share (node ids are identical in the single-image and the multi-view template), and one seed into every sampler."""
    P = load_presets()["parameters"]
    caps = load_presets()["intents"]["caps"]
    x, y = origin
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
        pos = (x, y + i * 150)
        if key in caps:   # post-processing values that the Output intent may lower
            m = math(g, title, table_capped(P[key], caps[key]), quality, "INDEX", pos, extra_in=[(output, "INDEX", "b")])
        else:
            m = math(g, title, table(P[key], key), quality, "INDEX", pos)
        if nid is not None:
            g.connect(m, "INT", nid, inp, dtype="INT", widget=True)
        else:
            tex_math = m
    # texture size replaces the template's single "Texture Resolution" primitive
    g.connect(tex_math, "INT", 196, "resolution", dtype="INT", widget=True)
    g.connect(tex_math, "INT", 147, "texture_size", dtype="INT", widget=True)
    g.remove(288)
    for ks in (3, 18, 23, 12):
        g.connect(seed, "INT", ks, "seed", dtype="INT", widget=True)


def _image_graph(subject: bool = False):
    """Patch the official template; returns (graph, ids) so the prompt app can reuse the 3D half.

    ``subject=True`` (the Image app) adds the Subject control: person/face detection, bust framing and the report."""
    up = json.loads((UPSTREAM / "3d_pixal3d_trellis2_image_to_model.json").read_text(encoding="utf-8"))
    g = Graph(up)
    X, Y = -5100, -1560  # control strip, top-left of the official graph

    # ---- public controls -------------------------------------------------------------------------
    model = combo(g, "Model", "Model", MODEL_OPTIONS, MODEL_OPTIONS[0], (X, Y),
                  "Auto uses Pixal3D. Choose TRELLIS.2 for complex or thin geometry.")
    quality = combo(g, "Quality", "Quality", QUALITY_OPTIONS, QUALITY_OPTIONS[1], (X + 360, Y),
                    "Fast = quick preview, Balanced = recommended, Maximum = most detail (needs the most GPU memory).")
    background = combo(g, "Background", "Background", BACKGROUND_OPTIONS, BACKGROUND_OPTIONS[0], (X + 720, Y),
                       "Auto removes the background. Keep uses your image's own transparency.")
    output = combo(g, "Output", "Output", INTENT_OPTIONS, INTENT_OPTIONS[0], (X + 1440, Y),
                   "High fidelity keeps all detail. Game asset caps polygons and textures; it re-uses the generated shape.")
    seed = g.add("PrimitiveInt", title="Seed", pos=(X + 1080, Y), size=(300, 110), widgets=[1234, "randomize"],
                 inputs=[{"name": "value", "type": "INT", "widget": {"name": "value"}, "label": "Seed", "localized_name": "value"}],
                 outputs=[{"name": "INT", "type": "INT", "localized_name": "INT"}])

    # ---- subject routing (Image app): what kind of problem is this picture? -------------------------------------------
    route = None
    if subject:
        subject_combo = combo(g, "Subject", "Subject", SUBJECT_OPTIONS, SUBJECT_OPTIONS[0], (X + 1800, Y),
                              "Auto looks for a face and picks Character bust for people; Object for everything else. Complex uses TRELLIS.2.")
        route = add_subject_routing(g, subject_combo, (X, Y + 1500))
        route["combo"] = subject_combo

    # ---- model switch: replaces the template's boolean ("true = TRELLIS.2") ---------------------------
    if route:   # Model = Auto follows the Subject (Complex -> TRELLIS.2); choosing a model yourself always wins
        is_trellis = math(g, "Model is TRELLIS.2?", "a == 2 or (a == 0 and b == 2)", model, "INDEX", (X, Y + 240),
                          extra_in=[(route["subject"], "INT", "b")])
    else:
        is_trellis = math(g, "Model is TRELLIS.2?", "a == 2", model, "INDEX", (X, Y + 240))
    for sw in (314, 315, 318):
        g.connect(is_trellis, "BOOL", sw, "switch", dtype="BOOLEAN", widget=True)
    g.remove(316)
    g.remove(317)  # markdown note that documented the removed boolean

    # ---- quality presets (one tiny table per parameter) and one seed for every sampler -----------------
    apply_quality(g, quality, output, seed, (X + 400, Y + 240))

    # ---- background handling: Auto = AI matte x your cutout, Remove = AI matte, Keep = your cutout --
    inv = g.add("InvertMask", title="Your cutout (alpha)", pos=(X + 800, Y + 240), size=(260, 60),
                inputs=[{"name": "mask", "type": "MASK"}], outputs=[{"name": "MASK", "type": "MASK"}])
    if route:   # the cutout of the BUST, not of the whole picture
        g.connect(route["crop_alpha"], 0, inv, "mask")
        g.connect(route["crop_img"], 0, 192, "image")
        g.connect(route["crop_img"], 0, 312, "images")
    else:
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
    g.nodes[322]["widgets_values"][0] = "models/image"   # -> <output folder>/models/image_00001.glb
    g.nodes[302]["title"] = "Prepared image (what the model sees)"
    g.nodes[122]["widgets_values"][0] = "Local3D_example_robot.jpg"  # copied into the input folder on first run
    g.label_widget(122, "image", "Image", "COMBO")

    # ---- documentation inside the graph -----------------------------------------------------------
    note(g, "## Local3D — Image to 3D\n\nThis graph is the official **Pixal3D & TRELLIS.2** workflow with a few "
            "Comfy Core nodes added for the app controls (Model, Quality, Background, Seed). The quality presets live in "
            "the *Preset* Math Expression nodes (generated from `data/presets.json`).\n\n"
            "Diagnostic previews are muted; un-mute them to inspect stages. Upstream: Comfy-Org/workflow_templates (MIT).",
         (X, Y - 380), (760, 260))
    g.group("Local3D controls (public app inputs)", X - 40, Y - 80, 1820, 460, "#8A8")
    g.group("Quality presets (data/presets.json)", X + 360, Y + 200, 380, 960, "#a1309b")
    g.group("Background handling", X + 780, Y + 200, 740, 800, "#b58b2a")

    enrich_upstream_models(g)
    describe_stages(g, IMAGE_STAGES)
    ids = {"model": model, "quality": quality, "output": output, "background": background, "seed": seed, "bg_nodes": [inv, auto_mask, bg_is_remove, bg_is_keep, sw_remove]}
    if route:
        ids["subject"] = route["combo"]
        ids["report"] = route["report"]
    return g, ids


def build_image_app() -> dict:
    g, ids = _image_graph(subject=True)
    inputs = [  # descriptions stay under ~34 characters: App Mode shows them on a single line
        [122, "image", {"description": "Drop ONE subject in frame"}],
        [ids["subject"], "choice", {"description": "Auto picks for your picture"}],
        [ids["model"], "choice", {"description": "Auto = Pixal3D (recommended)"}],
        [ids["quality"], "choice", {"description": "Balanced is recommended"}],
        [ids["output"], "choice", {"description": "Game asset = ~30k triangles"}],
        [ids["background"], "choice", {"description": "Keep needs a transparent PNG"}],
        [ids["seed"], "value", {"description": "Same seed = same result"}],
    ]
    app_meta(g, "image-to-3d", inputs, [322, 302, ids["report"]])
    return g.finish("image-to-3d")


# --------------------------------------------------------------------------------------------------
# Character from views app: Pixal3D multi-view on 2 to 4 REAL views of the same subject (official template, patched)
# --------------------------------------------------------------------------------------------------
VIEWS_OPTIONS = ["All four views — best", "Front + back only"]
VIEW_FILES = {"front": "Local3D_example_views_front.jpg", "left": "Local3D_example_views_left.jpg",
              "back": "Local3D_example_views_back.jpg", "right": "Local3D_example_views_right.jpg"}
VIEWS_STAGES = {
    192: "Cutting out the front view", 348: "Cutting out the left view", 351: "Cutting out the back view", 353: "Cutting out the right view",
    312: "Preparing the front view", 349: "Preparing the left view", 350: "Preparing the back view", 352: "Preparing the right view",
    15: "Loading models", 193: "Loading models", 117: "Loading models", 118: "Loading models", 319: "Loading models",
    3: "Generating coarse geometry", 119: "Generating coarse geometry", 87: "Generating coarse geometry",
    91: "Refining geometry", 18: "Refining geometry", 94: "Refining geometry", 23: "Refining geometry", 92: "Refining geometry",
    98: "Generating materials", 12: "Generating materials", 93: "Generating materials",
    202: "Cleaning up the mesh", 241: "Cleaning up the mesh", 186: "Simplifying the mesh", 238: "Processing the mesh",
    196: "Unwrapping textures", 147: "Baking colour textures", 224: "Baking surface detail", 233: "Baking shading",
    210: "Packing the model", 260: "Packing the model", 285: "Packing the model", 372: "Saving the model",
}


def build_views_app() -> dict:
    up = json.loads((UPSTREAM / "3d_pixal3d_multi_views.json").read_text(encoding="utf-8"))
    g = Graph(up)
    X, Y = -5100, -1560

    # ---- the template cuts ONE turnaround sheet into four views; the app takes four pictures instead ----------------
    for nid in (364, 338, 341, 342, 345, 374, 376):
        g.remove(nid)
    loaders = {}
    labels = {"front": "Front view", "left": "Left view", "back": "Back view", "right": "Right view"}
    for i, view in enumerate(("front", "left", "back", "right")):
        loaders[view] = g.add(
            "LoadImage", title=labels[view], pos=(X + i * 360, Y + 620), size=(330, 360), widgets=[VIEW_FILES[view], "image"],
            inputs=[{"name": "image", "type": "COMBO", "widget": {"name": "image"}, "label": "Image", "localized_name": "image"},
                    {"name": "upload", "type": "IMAGEUPLOAD", "widget": {"name": "upload"}}],
            outputs=[{"name": "IMAGE", "type": "IMAGE"}, {"name": "MASK", "type": "MASK"}])
        g.label_widget(loaders[view], "image", labels[view], "COMBO")
    cut = {"front": (192, 312), "left": (348, 349), "back": (351, 350), "right": (353, 352)}   # (RemoveBackground, ImageCropToMask)
    for view, (rb, crop) in cut.items():
        g.connect(loaders[view], 0, rb, "image")
        g.connect(loaders[view], 0, crop, "images")
    # the template saved each prepared view to disk on its way into the conditioning: connect them directly instead
    for nid in (340, 343, 344, 346):
        g.remove(nid)
    for view, (rb, crop) in cut.items():
        g.connect(crop, 0, 324, view)

    # ---- two conditioning variants; the control picks one (the other is never executed: the switch is lazy) --------------
    cond4 = 324
    n324 = g.nodes[324]
    cond2 = g.add("Pixal3DMultiViewConditioning", title="Pixal3D Multi-View Conditioning (front + back)", pos=(n324["pos"][0], n324["pos"][1] + 420),
                  size=n324["size"], widgets=[20.0],
                  inputs=[{"name": "clip_vision_model", "type": "CLIP_VISION"}],
                  outputs=[{"name": "positive", "type": "CONDITIONING"}, {"name": "negative", "type": "CONDITIONING"}])
    g.connect(15, 0, cond2, "clip_vision_model")
    g.connect(cut["front"][1], 0, cond2, "front", dtype="IMAGE")
    g.connect(cut["back"][1], 0, cond2, "back", dtype="IMAGE")
    views_combo = combo(g, "Views", "Views", VIEWS_OPTIONS, VIEWS_OPTIONS[0], (X + 1440, Y + 620),
                        "All four views gives the best model. With only a front and a back picture, choose Front + back only.")
    only_two = math(g, "Front + back only?", "a == 1", views_combo, "INDEX", (X + 1440, Y + 860))
    for out_slot, nm in ((0, "positive"), (1, "negative")):
        sw = g.add("ComfySwitchNode", title=f"Switch: views ({nm})", pos=(n324["pos"][0] + 420, n324["pos"][1] + out_slot * 110), size=(280, 100),
                   widgets=[False], inputs=[{"name": "on_false", "type": "CONDITIONING", "shape": 7}, {"name": "on_true", "type": "CONDITIONING", "shape": 7}],
                   outputs=[{"name": "output", "type": "CONDITIONING"}])
        g.connect(cond4, out_slot, sw, "on_false")
        g.connect(cond2, out_slot, sw, "on_true")
        g.connect(only_two, "BOOL", sw, "switch", dtype="BOOLEAN", widget=True)
        for consumer in (3, 91):   # the sampler and the shape stage read the conditioning
            g.connect(sw, 0, consumer, nm)

    # ---- controls shared with the Image app ----------------------------------------------------------------------------
    quality = combo(g, "Quality", "Quality", QUALITY_OPTIONS, QUALITY_OPTIONS[1], (X, Y), "Fast = quick preview, Balanced = recommended, Maximum = most detail.")
    output = combo(g, "Output", "Output", INTENT_OPTIONS, INTENT_OPTIONS[0], (X + 360, Y),
                   "High fidelity keeps all detail. Game asset caps polygons and textures; it re-uses the generated shape.")
    seed = g.add("PrimitiveInt", title="Seed", pos=(X + 720, Y), size=(300, 110), widgets=[1234, "randomize"],
                 inputs=[{"name": "value", "type": "INT", "widget": {"name": "value"}, "label": "Seed", "localized_name": "value"}],
                 outputs=[{"name": "INT", "type": "INT", "localized_name": "INT"}])
    apply_quality(g, quality, output, seed, (X + 400, Y + 240))

    # ---- app outputs: the model and what the model saw ------------------------------------------------------------------
    previews = {}
    for i, view in enumerate(("front", "left", "back", "right")):
        previews[view] = g.add("PreviewImage", title=f"Prepared {view} view (what the model sees)", pos=(X + 2200, Y + i * 330), size=(300, 300),
                               inputs=[{"name": "images", "type": "IMAGE"}], outputs=[{"name": "IMAGE", "type": "IMAGE"}])
        g.connect(cut[view][1], 0, previews[view], "images")
    g.mute(246, 323, 262, 261)
    g.nodes[372]["widgets_values"][0] = "models/views"   # -> <output folder>/models/views_00001.glb
    g.nodes[372]["title"] = "Save 3D model"

    note(g, "## Local3D — Character from views\n\nThis graph is the official **Pixal3D multi-view** workflow. Instead of one turnaround sheet it takes "
            "four separate pictures of the SAME subject (front, left, back, right: the camera moves 90 degrees between views, same distance, "
            "same pose). Each picture is cut out and framed on its own, exactly as the template does. *Front + back only* uses just two views.\n\n"
            "Generated or invented views are NOT a substitute: if the views disagree, the model averages them and the result gets blurry or warped "
            "(measured in docs/CHARACTER_ROUTING_DECISION.md). Upstream: Comfy-Org/workflow_templates (MIT).", (X, Y - 380), (860, 300))
    g.group("Local3D controls (public app inputs)", X - 40, Y - 80, 1100, 280, "#8A8")
    g.group("The four views (public app inputs)", X - 40, Y + 580, 1480, 440, "#a1309b")
    enrich_upstream_models(g)
    describe_stages(g, VIEWS_STAGES)
    inputs = [
        [loaders["front"], "image", {"description": "Front of the subject"}],
        [loaders["left"], "image", {"description": "Subject's left side"}],
        [loaders["back"], "image", {"description": "Back of the subject"}],
        [loaders["right"], "image", {"description": "Subject's right side"}],
        [views_combo, "choice", {"description": "Front + back needs just two"}],
        [quality, "choice", {"description": "Balanced is recommended"}],
        [output, "choice", {"description": "Game asset = ~30k triangles"}],
        [seed, "value", {"description": "Same seed = same result"}],
    ]
    app_meta(g, "character-from-views", inputs, [372] + [previews[v] for v in ("front", "left", "back", "right")])
    return g.finish("character-from-views")


# --------------------------------------------------------------------------------------------------
# Prompt -> reference image stage (FLUX.2 klein 4B distilled; parameters copied from the official template)
# --------------------------------------------------------------------------------------------------
# Chosen by measurement (scripts/evaluate_prompts.py, see docs/QUALITY.md): with this wording 96% of generated pictures
# passed the framing check, against 48% for the raw prompt and 70% for the first wording we tried.
PROMPT_SUFFIX = (", a single complete object, small in the frame with a wide empty margin of plain background on every side, "
                 "fully visible and not cropped, three-quarter front view from slightly above, soft even studio lighting, "
                 "seamless neutral grey background, clean unmarked surfaces, photorealistic 3D render")
DEFAULT_PROMPT = "A vintage red metal toolbox with a folding carry handle"
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
    describe_stages(g, {unet: "Loading the picture model", clip: "Loading the picture model", vae: "Loading the picture model",
                        enc: "Reading your prompt", sample: "Drawing the reference picture", decode: "Finishing the picture"})
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
    describe_stages(g, {ref: "Saving the reference picture"})
    g.nodes[322]["widgets_values"][0] = "models/prompt"
    inputs = [
        [prompt, "value", {"description": "Describe ONE object"}],
        [friendly, "value", {"description": "Adds framing that helps 3D"}],
        [ids["model"], "choice", {"description": "Auto = Pixal3D (recommended)"}],
        [ids["quality"], "choice", {"description": "Balanced is recommended"}],
        [ids["output"], "choice", {"description": "Game asset = ~30k triangles"}],
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
    describe_stages(g, {out: "Saving the pictures"})
    note(g, "## Local3D — Reference pictures\n\nMake a few reference pictures from a prompt, pick the best one, then open "
            "**Image to 3D** and choose it there (press **R** to refresh its picture list). Pictures are saved as `Local3D_reference_*.png`.", (X, Y - 330), (700, 200))
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
    "example_workflows/Local3D_Character_from_Views.app.json": build_views_app,
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
