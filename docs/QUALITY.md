# Quality presets and evaluation

Everything here was **measured**, not assumed. The tools that produced the numbers are in the repository
(`scripts/bench_presets.py`, `scripts/evaluate_samples.py`) so you can repeat them on your own hardware.

## How the presets were chosen

*Maximum* is exactly the official Comfy-Org template default: the settings the model authors validated. *Balanced* and
*Fast* change only the knobs that cost memory and time without changing the model or the sampling steps. The single
source of truth is [`data/presets.json`](../data/presets.json); the apps are generated from it.

| Setting (what it controls) | Fast | **Balanced** | Maximum |
| --- | --- | --- | --- |
| Shape detail: refined voxel grid | 1024 | **1536** | 1536 |
| Clean-up remesh grid | 512 | **768** | 768 |
| Polygon budget of the exported mesh | 100 k | **300 k** | 700 k |
| Colour / metallic / roughness texture | 2048 px | **2048 px** | 4096 px |
| Normal map | 1024 px | **2048 px** | 2048 px |
| Ambient-occlusion map | 512 px | **1024 px** | 1024 px |
| Diffusion steps | upstream (12 / 20 / 12 / 12) | **same** | same |

Why this shape: the 1536 shape grid is where detail comes from, so *Balanced* keeps it; the polygon budget and the 4096
texture are what make files and GPU memory large (the UV-unwrap and texture-bake stages are the heaviest), so *Balanced* trims
those. *Fast* also drops the shape grid to 1024, which is Pixal3D's own low-memory setting. The sampler step counts are never
reduced: fewer steps visibly hurt quality for little time saved.

## Measured results

NVIDIA RTX 5080 (16 GB), Windows 11, ComfyUI 0.38.0, torch 2.14.0+cu130, models already loaded (warm), a different
seed per run, one 1024 px picture (a detailed axe). Other programs held 3 to 10 GB of the GPU's memory during these runs.

| Quality | Pixal3D time | Pixal3D mesh | TRELLIS.2 time | TRELLIS.2 mesh |
| --- | --- | --- | --- | --- |
| Fast | **38 s** | 100 k triangles, 13 MB GLB | 53 s | 97 k triangles, 15 MB |
| **Balanced** | **81 s** | 299 k triangles, 30 MB | 137 s | 295 k triangles, 30 MB |
| Maximum | **111 s** | 698 k triangles, 68 MB | 145 s | 692 k triangles, 67 MB |

All six runs finished without running out of memory. The GPU's total memory use peaked at about 14 to 15 GB of 16 GB
while ComfyUI was working: ComfyUI's *dynamic VRAM* uses whatever is free and moves model weights in and out as
needed, so the peak shows what was *available*, not the minimum required. We could not test cards with less memory;
reports from other users of the same pipeline show 12 GB cards running out of memory at the old *Maximum* settings
(a fix landed upstream in ComfyUI 0.35, which Local3D includes), and a 16 GB card finishing at the defaults.
**On 12 GB or less start with *Fast* or *Balanced*.**

Look at what you get: *Fast* is a real preview, not a degraded one. In the independent viewer the 100 k-triangle axe keeps the wolf
head, legible runes and the wrapped handle; *Balanced* adds finer surface and 2048-px normal detail; *Maximum* mostly adds
polygon count and a 4096-px colour map.

## Mesh and file checks

The exported GLB was validated with the Khronos glTF Validator: one mesh, one PBR material, embedded PNG textures
(base colour, metallic-roughness, normal, occlusion), UVs, and correct accessors. The single finding is **54
near-zero normals out of 454,949 vertices** (0.012 %) from ComfyUI's normal-smoothing step. Renderers renormalise them, so nothing is
visibly wrong; it is an upstream cosmetic issue.

Known geometry limits (upstream, not specific to Local3D): the hidden back side is *estimated*; thin parts can merge or
disappear; meshes can contain an inner shell (invisible when viewing, relevant for 3D printing, ComfyUI issue #16147).

## Reference pictures for Prompt to 3D

A pretty picture is not automatically a good 3D reference. The 3D models first cut the object out, centre it and
re-frame it, so the picture needs one complete object, clear of the borders, on a plain background. The *3D-friendly*
option adds one fixed sentence to the prompt for exactly that, and `evaluate_samples.py` checks every candidate
automatically for: object touching the border (cropped), object size in frame (35 to 92 % of the picture) and background
noise. It does not judge the artwork.

## Evaluation set

EVALUATION_PLACEHOLDER

## Repeat it

```
python scripts/bench_presets.py --capture <api prompt json> --output-dir <ComfyUI output> --matrix Fast:Auto,Balanced:Auto,Maximum:Auto
python scripts/evaluate_samples.py --captures <dir> --input-dir <ComfyUI input> --output-dir <ComfyUI output>
```
See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to capture an app's API prompt.
