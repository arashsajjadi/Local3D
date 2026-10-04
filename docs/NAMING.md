# Naming

**Decision: the product and repository are named `Local3D`.**
Evidence date: 2026-10-04.

## Why

- Short, obvious, easy to spell and search; says what it is (local 3D generation) before the README is read.
- Available where it matters:
  `github.com/arashsajjadi/Local3D` was free (the repository was created for this project afterwards), and the handles `Local3D`/`local3d`
  were unclaimed on GitHub, PyPI, npm, crates.io, Docker Hub and Hugging Face.
- No major active software product, company or registered trademark named *Local3D* turned up.

## Honest caveats

- The exact string is not unique on the wider web: a few zero-star GitHub repos use it (one is a Pixal3D image-to-GLB
  app created in September 2026, without a license), `local3d.io` is an unrelated browser file-converter, and
  `local3d.com`/`.app` are registered domains. None is a major or confusable product.
- *Local + 3D* is descriptive, so it is a weak trademark either way. No USPTO/CIPO knock-out search was possible from
  here; do one before any commercial launch.
- The niche is not empty: `lightningpixel/modly` (a desktop "local image/prompt to 3D" app) is the popular incumbent.
  Local3D differs by being a thin layer on official ComfyUI core with PBR GLB output and no custom inference stack.

## Rejected alternatives

| Name | Why not |
| --- | --- |
| `Local3DGen` | live near-duplicates (`local-3dgen`, `L3DGen`) |
| `OpenLocal3D` | zero collisions, but reads like an add-on to Open3D |

## Not affiliated

Local3D is an independent project. It is **not affiliated with or endorsed by** Comfy Org / ComfyUI, Microsoft,
Tencent, Meta, Black Forest Labs, or LocalAI. Those names are used only to identify the upstream projects it runs on.

## Repository metadata

- **Description:** *Local3D — turn a photo or a text prompt into a textured 3D model (GLB) offline on your own NVIDIA GPU;
  a one-click Windows app built on ComfyUI. MIT licensed.*
- **Topics:** `image-to-3d`, `text-to-3d`, `3d-generation`, `comfyui`, `trellis`, `local-ai`, `offline`, `windows`,
  `desktop-app`, `glb`, `generative-ai`, plus `pixal3d`/`trellis2` (both ship). Topic choice follows real usage counts
  (e.g. `image-to-3d` 283, `3d-generation` 367, `comfyui` ~3.3k repos).
