#!/usr/bin/env python3
"""Measure what a GLB really contains (dev tool for the evaluation scripts; needs ``pip install trimesh numpy pillow``).

    python scripts/mesh_report.py model.glb [more.glb ...] [--json]

Reported: triangles, vertices, bounding box, connected components (and the share of triangles outside the largest one),
open (boundary) edges, non-manifold edges, watertightness, volume when closed, and the embedded texture maps.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def report(path: str | Path) -> dict:
    import trimesh

    path = Path(path)
    scene = trimesh.load(path, force="scene", process=False)
    meshes = [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]
    if not meshes:
        raise ValueError(f"{path} contains no triangle mesh")
    mesh = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
    # UV seams split vertices: weld by position first, so "open edge" means a real hole, not a texture seam
    geo = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=False)
    geo.merge_vertices(digits_vertex=6)
    geo.update_faces(geo.nondegenerate_faces())
    mesh = geo
    faces = mesh.faces
    edges = np.sort(mesh.edges, axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    open_edges = int((counts == 1).sum())
    nonmanifold = int((counts > 2).sum())
    comps = trimesh.graph.connected_components(mesh.face_adjacency, nodes=np.arange(len(faces)), min_len=1)
    sizes = sorted((len(c) for c in comps), reverse=True)
    textures = {}
    for g in meshes:
        mat = getattr(getattr(g, "visual", None), "material", None)
        for name in ("baseColorTexture", "metallicRoughnessTexture", "normalTexture", "occlusionTexture", "emissiveTexture"):
            img = getattr(mat, name, None)
            if img is not None:
                textures[name] = list(img.size)
    return {
        "file": path.name, "mb": round(path.stat().st_size / 1e6, 1), "triangles": int(len(faces)), "vertices": int(len(mesh.vertices)),
        "bbox_m": [round(float(v), 4) for v in mesh.extents],
        "components": len(sizes), "largest_component_share": round(sizes[0] / len(faces), 4) if sizes else 1.0,
        "floater_triangles": int(len(faces) - sizes[0]) if sizes else 0,
        "open_edges": open_edges, "open_edge_share": round(open_edges / max(1, len(edges)), 5), "nonmanifold_edges": nonmanifold,
        "watertight": bool(open_edges == 0 and nonmanifold == 0), "volume_cm3": round(float(mesh.volume) * 1e6, 1) if open_edges == 0 else None,
        "textures": textures,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("glb", nargs="+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rows = [report(p) for p in a.glb]
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        for r in rows:
            print(f"{r['file']}: {r['triangles']:,} tris, {r['mb']} MB, bbox {r['bbox_m']} m, {r['components']} component(s) "
                  f"({r['floater_triangles']} floater tris), {r['open_edges']} open edges ({r['open_edge_share'] * 100:.2f}%), "
                  f"{'WATERTIGHT' if r['watertight'] else 'not watertight'}, textures {r['textures']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
