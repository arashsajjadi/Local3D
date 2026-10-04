# Vendored upstream workflows

Unmodified copies of three official templates, taken from the `comfyui-workflow-templates` package (version **0.11.70**)
that ships inside the pinned ComfyUI runtime (see `data/runtime.json`). They are the source of truth for every
model-correctness detail; `scripts/build_workflows.py` only patches them.

| File | Upstream template | License |
| --- | --- | --- |
| `3d_pixal3d_trellis2_image_to_model.json` | "Pixal3D & TRELLIS.2: Image to Model" | MIT (Comfy-Org/workflow_templates) |
| `3d_pixal3d_multi_views.json` | "Pixal3D: Multi-view to Model" (source of the *Character from views* app) | MIT (Comfy-Org/workflow_templates) |
| `image_flux2_klein_text_to_image.json` | "FLUX.2 [klein] 4B: Text to Image" (its *distilled* subgraph supplies the parameters used for reference pictures) | MIT (Comfy-Org/workflow_templates) |

Sample input images that some upstream templates reference are **not** redistributed here.

## Refreshing

1. Bump the runtime in `data/runtime.json` and install it.
2. Copy the same three files from
   `python_embeded/Lib/site-packages/comfyui_workflow_templates_json/templates/` of that runtime.
3. `python scripts/build_workflows.py`, then re-run the app tests and `scripts/bench_presets.py`.
