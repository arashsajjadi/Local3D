#!/usr/bin/env python3
"""Validate the Local3D repository (stdlib only; no GPU, no ComfyUI install needed).

    python scripts/validate.py

Checks: JSON validity, workflow graph integrity, App Mode schema, core-nodes-only, model metadata vs the hash-pinned
manifest, preset/app consistency, version consistency, repository hygiene (secrets, personal paths, big binaries),
and relative Markdown links. Exits 1 and prints every problem when something is wrong.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []
notes: list[str] = []


def err(msg: str):
    errors.append(msg)


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        err(f"{path.relative_to(ROOT)}: invalid JSON ({e})")
        return None


# ---------------------------------------------------------------------------------------------- data files
def check_data():
    manifest = load(ROOT / "data" / "models.json")
    runtime = load(ROOT / "data" / "runtime.json")
    presets = load(ROOT / "data" / "presets.json")
    core = load(ROOT / "data" / "core_node_types.json")
    load(ROOT / "data" / "frontend-settings.json")
    known_dirs = {"diffusion_models", "vae", "clip_vision", "text_encoders", "geometry_estimation", "background_removal", "checkpoints", "detection", "loras"}
    if manifest:
        packs = set(manifest.get("packs", {}))
        seen = set()
        for f in manifest["files"]:
            tag = f"models.json[{f.get('id')}]"
            if f["id"] in seen:
                err(f"{tag}: duplicate id")
            seen.add(f["id"])
            if f["pack"] not in packs:
                err(f"{tag}: unknown pack {f['pack']!r}")
            if not re.fullmatch(r"[0-9a-f]{64}", f["sha256"]):
                err(f"{tag}: sha256 must be 64 hex characters")
            if not re.fullmatch(r"[0-9a-f]{40}", f["revision"]):
                err(f"{tag}: revision must be a 40-character commit hash (pinned)")
            if not isinstance(f["size"], int) or f["size"] <= 0:
                err(f"{tag}: size must be a positive integer")
            if f["dest"].split("/")[0] not in known_dirs:
                err(f"{tag}: unexpected destination folder {f['dest']!r}")
            for g in f.get("gpu", []):
                if g not in manifest.get("gpu_classes", {}):
                    err(f"{tag}: unknown gpu class {g!r}")
        # every GPU class must resolve to exactly one diffusion model, text encoder and VAE in the prompt pack
        for cls in manifest.get("gpu_classes", {}):
            chosen = [f for f in manifest["files"] if f["pack"] == "prompt" and (not f.get("gpu") or cls in f["gpu"])]
            for kind in ("diffusion_models", "text_encoders", "vae"):
                n = sum(1 for f in chosen if f["dest"].startswith(kind + "/"))
                if n != 1:
                    err(f"models.json: prompt pack for gpu class {cls!r} has {n} files in {kind}/ (need exactly 1)")
    if runtime:
        if not re.fullmatch(r"[0-9a-f]{64}", runtime["sha256"]):
            err("runtime.json: sha256 must be 64 hex characters")
        if runtime["tag"] not in runtime["url"] or runtime["asset"] not in runtime["url"]:
            err("runtime.json: url must contain the pinned tag and asset name")
        if not runtime["url"].startswith("https://github.com/Comfy-Org/ComfyUI/releases/download/"):
            err("runtime.json: runtime must come from the official Comfy-Org/ComfyUI release page")
    if presets:
        n = len(presets["levels"])
        for k, v in presets["parameters"].items():
            if len(v) != n or not all(isinstance(x, int) and x > 0 for x in v):
                err(f"presets.json[{k}]: need {n} positive integers")
            if v != sorted(v):
                err(f"presets.json[{k}]: values must not decrease from Fast to Maximum ({v})")
        routing = presets.get("routing", {})
        for k in ("face_score_min", "person_score_min", "portrait_face_fraction", "bust_min_face_fraction", "bust_cut_face_heights", "bust_cut_max_fraction", "bust_min_gain"):
            if not isinstance(routing.get(k), (int, float)) or routing[k] <= 0:
                err(f"presets.json routing.{k}: must be a positive number")
        if routing and not 0 < routing.get("bust_min_face_fraction", 0) < routing.get("portrait_face_fraction", 0) <= 1:
            err("presets.json routing: bust_min_face_fraction must be positive and smaller than portrait_face_fraction, which must not exceed 1")
        if routing and not 0 < routing.get("bust_cut_max_fraction", 0) <= 1:
            err("presets.json routing.bust_cut_max_fraction: must be between 0 and 1")
        intents = presets.get("intents", {})
        for k, cap in intents.get("caps", {}).items():
            if k not in presets["parameters"] or not isinstance(cap, int) or cap <= 0:
                err(f"presets.json intents.caps[{k}]: must name a preset parameter and be a positive integer")
    if core and runtime and core.get("comfyui_version") != runtime.get("comfyui_version"):
        err("core_node_types.json was generated for a different ComfyUI version than data/runtime.json")
    return manifest, core


# ---------------------------------------------------------------------------------------------- workflows
OUTPUT_TYPES = {"SaveImage", "Save3DAdvanced", "SaveGLB", "PreviewImage"}   # App Mode shows picture and 3D outputs; text (PreviewAny) is not listed
WIDGET_FOR_TYPE = {"CustomCombo": "choice", "PrimitiveInt": "value", "PrimitiveStringMultiline": "value",
                   "PrimitiveBoolean": "value", "LoadImage": "image"}


def check_graph(rel: str, d: dict, core_types: set[str]):
    if d.get("version") != 0.4:
        err(f"{rel}: unsupported workflow schema version {d.get('version')!r} (expected 0.4)")
    nodes = {n["id"]: n for n in d.get("nodes", [])}
    subgraph_ids = {s["id"] for s in d.get("definitions", {}).get("subgraphs", [])}
    ids = set(nodes)
    for l in d.get("links", []):
        lid, s, ss, t, ts, _ = l
        if s not in ids or t not in ids:
            err(f"{rel}: link {lid} points at a missing node")
            continue
        outs, ins = nodes[s].get("outputs", []), nodes[t].get("inputs", [])
        if ss >= len(outs) or lid not in (outs[ss].get("links") or []):
            err(f"{rel}: link {lid} is not registered on node {s} output {ss}")
        if ts >= len(ins) or ins[ts].get("link") != lid:
            err(f"{rel}: link {lid} is not registered on node {t} input {ts}")
    for n in nodes.values():
        t = n["type"]
        if t not in core_types and t not in subgraph_ids:
            err(f"{rel}: node #{n['id']} uses '{t}', which is not a Comfy Core node (custom nodes are not allowed)")
        for out in n.get("outputs", []):
            for lid in out.get("links") or []:
                if not any(l[0] == lid for l in d["links"]):
                    err(f"{rel}: node #{n['id']} references missing link {lid}")


def check_app(rel: str, d: dict):
    extra = d.get("extra", {})
    if extra.get("linearMode") is not True:
        err(f"{rel}: extra.linearMode must be true for an App")
    data = extra.get("linearData") or {}
    nodes = {n["id"]: n for n in d["nodes"]}
    if not data.get("inputs") or not data.get("outputs"):
        err(f"{rel}: linearData needs inputs and outputs")
    for entry in data.get("inputs", []):
        nid, widget = entry[0], entry[1]
        n = nodes.get(nid)
        if n is None:
            err(f"{rel}: app input refers to missing node {nid}")
            continue
        if n.get("mode", 0) != 0:
            err(f"{rel}: app input node #{nid} is muted/bypassed")
        want = WIDGET_FOR_TYPE.get(n["type"])
        if want and widget != want:
            err(f"{rel}: app input #{nid} ({n['type']}) should expose widget {want!r}, not {widget!r}")
        desc = (entry[2] if len(entry) > 2 else {}).get("description", "")
        if len(desc) > 31:
            err(f"{rel}: description of input #{nid} is {len(desc)} characters; App Mode shows one line (<= 31)")
    for nid in data.get("outputs", []):
        n = nodes.get(nid)
        if n is None:
            err(f"{rel}: app output refers to missing node {nid}")
        elif n["type"] not in OUTPUT_TYPES:
            err(f"{rel}: app output #{nid} is {n['type']}; use a picture or Save node (3D only renders from SaveGLB/Save3DAdvanced, and App Mode lists no text outputs)")
    if not any(nodes[o]["type"] in {"Save3DAdvanced", "SaveGLB", "SaveImage"} for o in data.get("outputs", []) if o in nodes):
        err(f"{rel}: no Save output")
    if extra.get("local3d", {}).get("version") is None:
        err(f"{rel}: missing extra.local3d.version")


def check_models_in_graph(rel: str, d: dict, manifest: dict | None):
    if not manifest:
        return set()
    by_name = {f["dest"].split("/")[-1]: f for f in manifest["files"]}
    used = set()
    nodes = list(d["nodes"])
    for sg in d.get("definitions", {}).get("subgraphs", []):
        nodes += sg.get("nodes", [])
    for n in nodes:
        for m in n.get("properties", {}).get("models", []) or []:
            f = by_name.get(m["name"])
            if f is None:
                err(f"{rel}: node #{n['id']} embeds model '{m['name']}' which is not in data/models.json")
                continue
            used.add(f["id"])
            if not m["url"].startswith("https://huggingface.co/"):
                err(f"{rel}: model URL for {m['name']} must be a huggingface.co URL")
            if m.get("hash") != f["sha256"] or m.get("directory") != f["dest"].split("/")[0]:
                err(f"{rel}: model metadata for {m['name']} disagrees with data/models.json")
    return used


def check_workflows(manifest, core):
    core_types = set(core["node_types"]) | set(core.get("frontend_only", [])) if core else set()
    used_all: set[str] = set()
    apps = sorted((ROOT / "local3d_pack").rglob("*.app.json"))   # includes the per-GPU variants
    if not apps:
        err("local3d_pack/example_workflows has no *.app.json apps")
    for p in apps:
        d = load(p)
        if d is None:
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        check_graph(rel, d, core_types)
        check_app(rel, d)
        used_all |= check_models_in_graph(rel, d, manifest)
    for p in sorted((ROOT / "workflows" / "upstream").glob("*.json")):
        d = load(p)
        if d is not None:
            check_graph(str(p.relative_to(ROOT)).replace("\\", "/"), d, core_types)
    if manifest:
        for f in manifest["files"]:
            if f["id"] not in used_all:
                err(f"data/models.json: file {f['id']} is not referenced by any app")
    init = ROOT / "local3d_pack" / "__init__.py"
    if not init.exists():
        err("local3d_pack/__init__.py is missing (ComfyUI needs it to serve the apps)")
    elif re.search(r"^\s*(import|from)\s+(comfy|nodes|folder_paths|server)\b", init.read_text(encoding="utf-8"), re.M):
        err("local3d_pack/__init__.py must not import ComfyUI code")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_workflows.py"), "--check"], capture_output=True, text=True)
    if r.returncode != 0:
        err("apps are out of date with scripts/build_workflows.py or data/presets.json -> run: python scripts/build_workflows.py")


# ---------------------------------------------------------------------------------------------- versions
def check_versions():
    v = re.search(r'VERSION = "([^"]+)"', (ROOT / "scripts" / "build_workflows.py").read_text(encoding="utf-8"))
    version = v.group(1) if v else None
    cs = (ROOT / "launcher" / "Local3D.cs").read_text(encoding="utf-8")
    m = re.search(r'public const string Version = "([^"]+)"', cs)
    if not (version and m and m.group(1) == version):
        err(f"version mismatch: build_workflows.py={version} launcher={m.group(1) if m else None}")
    iss = ROOT / "installer" / "Local3D.iss"
    if iss.exists():
        mi = re.search(r'#define AppVersion "([^"]+)"', iss.read_text(encoding="utf-8"))
        if not (mi and mi.group(1) == version):
            err(f"version mismatch: installer={mi.group(1) if mi else None} vs {version}")
    ch = ROOT / "CHANGELOG.md"
    if ch.exists() and not re.search(rf"^## \[{re.escape(version)}\]", ch.read_text(encoding="utf-8"), re.M):
        err(f"CHANGELOG.md has no '## [{version}]' section (the release notes are built from it)")


# ---------------------------------------------------------------------------------------------- hygiene
SECRET_PATTERNS = {
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}", "Hugging Face token": r"hf_[A-Za-z0-9]{30,}",
    "API key": r"sk-[A-Za-z0-9]{32,}", "private key": r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----",
    "AWS key": r"AKIA[0-9A-Z]{16}", "GitHub fine-grained token": r"github_pat_[A-Za-z0-9_]{20,}",
    "Slack token": r"xox[baprs]-[A-Za-z0-9-]{10,}", "bearer token": r"Bearer\s+[A-Za-z0-9._~+/-]{24,}",
}
# domains an e-mail address may use in this repository (public noreply and placeholder addresses only)
EMAIL_OK = re.compile(r"(users\.noreply\.github\.com|noreply\.github\.com|anthropic\.com|example\.(com|org|net)|\.test|localhost)$", re.I)
AUTHOR_MACHINE = re.compile(r"Local3DData|Local3DModels|Scratch3D|[A-Za-z]:[\\/]New folder|AppData[\\/]Local[\\/]Temp[\\/]claude|scratchpad", re.I)
BAD_EXT = {".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".glb", ".gltf", ".obj", ".stl", ".exe", ".zip", ".7z", ".rar", ".dll"}
TEXT_EXT = {".md", ".json", ".py", ".cs", ".ps1", ".iss", ".yml", ".yaml", ".txt", ".toml", ".gitignore", ".gitattributes", ".svg", ""}


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        files = [ROOT / p for p in out.split("\0") if p]
        files += [ROOT / p for p in subprocess.run(["git", "ls-files", "-z", "--others", "--exclude-standard"], cwd=ROOT,
                                                      capture_output=True, text=True).stdout.split("\0") if p]
        return sorted(set(f for f in files if f.exists()))
    except Exception:  # noqa: BLE001 - not a git checkout (e.g. a release zip)
        return [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts and "build" not in p.parts]


def check_hygiene(files: list[Path]):
    for f in files:
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        if f.suffix.lower() in BAD_EXT:
            err(f"{rel}: binary/model/3D files must not be committed")
        if f.stat().st_size > 5_000_000:
            err(f"{rel}: larger than 5 MB ({f.stat().st_size / 1e6:.1f} MB)")
        if f.suffix.lower() in TEXT_EXT and f.name not in ("validate.py", "test_validate.py"):   # these two contain the patterns on purpose
            try:
                text = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            stray = sorted({hex(ord(ch)) for ch in text if (ord(ch) < 32 and ch not in "\t\n\r") or ord(ch) == 127})
            if stray:
                err(f"{rel}: contains control characters ({', '.join(stray)}): a backslash sequence that was turned into a character while the file was written?")
            for name, pat in SECRET_PATTERNS.items():
                if re.search(pat, text):
                    err(f"{rel}: looks like it contains a {name}")
            for m in re.finditer(r"[A-Za-z]:\\Users\\([A-Za-z0-9_.-]+)", text):
                if m.group(1).lower() not in {"user", "username", "you", "name", "public", "<user>", "your-name", "example"}:
                    err(f"{rel}: personal path 'C:\\Users\\{m.group(1)}' - use a generic example")
            for m in re.finditer(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})", text):
                if not EMAIL_OK.search(m.group(1)):
                    err(f"{rel}: contains an e-mail address ({m.group(0)}); only public noreply or example addresses belong in the repository")
            if AUTHOR_MACHINE.search(text):
                err(f"{rel}: mentions a path or folder name from the author's own machine")


def check_links(files: list[Path]):
    link = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
    for f in files:
        if f.suffix.lower() != ".md":
            continue
        text = f.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for target in link.findall(text):
            if re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                continue
            path = (f.parent / target.split("#")[0].split("?")[0]).resolve()
            if not path.exists():
                err(f"{f.relative_to(ROOT)}: broken link -> {target}")


def main() -> int:
    manifest, core = check_data()
    check_workflows(manifest, core)
    check_versions()
    files = tracked_files()
    check_hygiene(files)
    check_links(files)
    if errors:
        print(f"validate: {len(errors)} problem(s)")
        for e in errors:
            print("  -", e)
        return 1
    print(f"validate: OK ({len(files)} files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
