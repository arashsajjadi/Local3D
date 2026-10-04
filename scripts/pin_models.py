#!/usr/bin/env python3
"""Add or refresh model files in data/models.json from live Hugging Face metadata (dev tool; the result is committed).

Every entry is pinned to the repository's current commit and to the file's size and SHA-256 (the LFS object id), so the
launcher's downloader can verify it. Existing entries are left alone unless --refresh is given.

    python scripts/pin_models.py --pack multiview --id pixal3d-multiview-dit ^
        --repo Comfy-Org/Pixal3D --path diffusion_models/pixal3d_multiview_int8_convrot.safetensors ^
        --dest-dir diffusion_models --label "Pixal3D multi-view diffusion model (int8)" --license MIT [--note "..."] [--gpu blackwell,ada]

    python scripts/pin_models.py --show          # list packs and sizes
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent.parent / "data" / "models.json"


def _get(url: str):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def pin(repo: str, path: str) -> dict:
    sha = _get(f"https://huggingface.co/api/models/{repo}")["sha"]
    tree = {f["path"]: f for f in _get(f"https://huggingface.co/api/models/{repo}/tree/{sha}?recursive=true") if f["type"] == "file"}
    if path not in tree:
        raise SystemExit(f"{repo} has no file {path} at {sha[:8]}")
    f = tree[path]
    return {"revision": sha, "size": f["size"], "sha256": (f.get("lfs") or {}).get("oid", "")}


def show(m: dict) -> None:
    for pk, meta in m["packs"].items():
        files = [f for f in m["files"] if f["pack"] == pk]
        print(f"{pk:22s} {'required' if meta.get('required') else 'optional':9s} {sum(f['size'] for f in files) / 1e9:6.2f} GB  {len(files)} files  {meta['label']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--pack")
    ap.add_argument("--pack-label")
    ap.add_argument("--pack-required", action="store_true")
    ap.add_argument("--pack-description")
    ap.add_argument("--id")
    ap.add_argument("--repo")
    ap.add_argument("--path")
    ap.add_argument("--dest-dir")
    ap.add_argument("--label")
    ap.add_argument("--license")
    ap.add_argument("--note", default="")
    ap.add_argument("--gpu", default="")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if a.show:
        show(m)
        return 0
    for need in ("pack", "id", "repo", "path", "dest_dir", "label", "license"):
        if not getattr(a, need):
            ap.error(f"--{need.replace('_', '-')} is required")
    if a.pack not in m["packs"]:
        if not a.pack_label:
            ap.error(f"new pack {a.pack}: give --pack-label")
        m["packs"][a.pack] = {"label": a.pack_label, "required": a.pack_required}
        if a.pack_description:
            m["packs"][a.pack]["description"] = a.pack_description
    existing = next((f for f in m["files"] if f["id"] == a.id), None)
    if existing and not a.refresh:
        print(f"{a.id} is already in the manifest (use --refresh to re-pin it)")
        return 0
    entry = {"id": a.id, "pack": a.pack, "label": a.label, "license": a.license, "repo": a.repo, **pin(a.repo, a.path),
             "path": a.path, "dest": f"{a.dest_dir}/{a.path.rsplit('/', 1)[-1]}"}
    if a.gpu:
        entry["gpu"] = a.gpu.split(",")
    if a.note:
        entry["note"] = a.note
    # keep the same key order as the existing entries
    order = ["id", "pack", "label", "license", "repo", "revision", "path", "dest", "size", "sha256", "gpu", "note"]
    entry = {k: entry[k] for k in order if k in entry}
    if existing:
        m["files"][m["files"].index(existing)] = entry
    else:
        m["files"].append(entry)
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"pinned {a.id}: {entry['size'] / 1e9:.2f} GB, sha256 {entry['sha256'][:12]}..., rev {entry['revision'][:8]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
