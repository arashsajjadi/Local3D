# Third-party notices

Local3D itself is MIT-licensed (see [LICENSE](LICENSE)). That license covers **only the files in this repository**.
Local3D runs, but does not contain or modify, the software and models below. Each has its own license, which applies
to you when you download and use it. This is a good-faith summary, not legal advice; the linked originals are authoritative.

Local3D is an independent project. It is **not affiliated with or endorsed by** Comfy Org, Microsoft, Tencent, Meta,
Black Forest Labs, Alibaba, NVIDIA or anyone else listed here.

## 1. Content derived from upstream (included in this repository)

| Component | What we include | License |
| --- | --- | --- |
| [Comfy-Org/workflow_templates](https://github.com/Comfy-Org/workflow_templates) | `workflows/upstream/*.json` are unmodified copies of three official templates; `local3d_pack/example_workflows/*.app.json` and `local3d_pack/variants/*/*.app.json` are generated from them by `scripts/build_workflows.py` | MIT, see below |

```
MIT License

Copyright (c) 2023-present Comfy Org

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The example pictures in `assets/examples/` were generated with FLUX.2 [klein] 4B (Apache-2.0) from prompts written for
this project; they contain no third-party artwork. The four `Local3D_example_views_*` pictures are renders (from four sides) of a
3D model that Local3D itself generated from one of those pictures. The nine evaluation pictures in `assets/eval/` (subject-routing checks;
not installed) were also generated with FLUX.2 [klein] 4B from the prompts listed beside them, and the people in them are synthetic. Sample input images used by some upstream templates are not redistributed. The benchmark picture behind `docs/images/axe-presets.jpg` is
`viking_wolf_rune_axe.png` from Comfy-Org/workflow_templates (MIT); that figure shows Local3D renders of models generated from it, and the PNG itself is not in this repository.

## 2. Runtime downloaded on first start (not included in this repository or the installer)

| Component | Source | License |
| --- | --- | --- |
| ComfyUI (server and core nodes) | [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI), official Windows portable release, pinned in `data/runtime.json`, checksum-verified | GPL-3.0 |
| ComfyUI frontend (the App Mode UI, 3D viewer) | bundled in the portable build ([Comfy-Org/ComfyUI_frontend](https://github.com/Comfy-Org/ComfyUI_frontend)) | GPL-3.0 |
| comfy-aimdo | bundled in the portable build | GPL-3.0 |
| comfy-kitchen; huggingface_hub (used by `scripts/provision_models.py` to download models) | bundled in the portable build | Apache-2.0 |
| Python, PyTorch, NVIDIA CUDA runtime libraries and other wheels | bundled in the portable build | PSF, BSD-3-Clause, NVIDIA CUDA EULA, and the respective package licenses |

ComfyUI is started as a **separate, unmodified process**. This repository contains no ComfyUI code: the
`local3d_pack` folder holds only workflow JSON and an `__init__.py` that imports nothing from ComfyUI.

System components used as-is: `curl.exe` and `tar.exe` (Windows), Microsoft Edge (shows the app window; its
license is Microsoft's, nothing is redistributed).

## 3. AI models downloaded on first start (never stored in this repository)

Models are fetched from Hugging Face by Local3D's provisioning step, pinned to exact revisions and SHA-256 hashes
(`data/models.json`). **Model licenses differ from the application license.**

| Model | Used for | License |
| --- | --- | --- |
| [Pixal3D](https://huggingface.co/TencentARC/Pixal3D) (TencentARC); ComfyUI repack: [Comfy-Org/Pixal3D](https://huggingface.co/Comfy-Org/Pixal3D) | image to 3D (default) | MIT. **Note:** earlier versions of the upstream weights carried an academic-only license; MIT applies since 2026-05-20 |
| [TRELLIS.2](https://github.com/microsoft/TRELLIS.2) (Microsoft); repack: [Comfy-Org/TRELLIS.2](https://huggingface.co/Comfy-Org/TRELLIS.2) | image to 3D (alternative) | MIT |
| DINOv3 ViT-L image encoder (Meta), repacked in [Comfy-Org/Pixal3D](https://huggingface.co/Comfy-Org/Pixal3D) | conditioning for both 3D models | **Meta DINOv3 License (custom, not MIT).** Read it at <https://ai.meta.com/resources/models-and-libraries/dinov3-license/>. It includes redistribution, trade-control and military end-use terms. Local3D downloads the file for you directly from Hugging Face and does not redistribute it. The same file also bundles the NAF feature-upsampler weights ([valeoai/NAF](https://github.com/valeoai/NAF), Apache-2.0) |
| [BiRefNet](https://huggingface.co/ZhengPeng7/BiRefNet) (Peng Zheng et al.); repack: [Comfy-Org/BiRefNet](https://huggingface.co/Comfy-Org/BiRefNet) | background removal | MIT |
| [MoGe-2](https://github.com/microsoft/MoGe) (Microsoft); repack: [Comfy-Org/MoGe](https://huggingface.co/Comfy-Org/MoGe) | camera / field-of-view estimation | MIT (code), includes DINOv2 code under Apache-2.0 |
| RT-DETR v4 (X, fp16): original [RT-DETRv4](https://github.com/RT-DETRs/RT-DETRv4); ComfyUI repack: [Comfy-Org/SDPose](https://huggingface.co/Comfy-Org/SDPose) | finds a person, for subject routing | Apache-2.0 (original); the Comfy-Org repack is MIT |
| MediaPipe face detector and landmarker (Google); repack: [Comfy-Org/mediapipe](https://huggingface.co/Comfy-Org/mediapipe) | finds a face, for subject routing | Apache-2.0 |
| Pixal3D multi-view model (TencentARC), ComfyUI repack in [Comfy-Org/Pixal3D](https://huggingface.co/Comfy-Org/Pixal3D) | *Character from views* (optional download) | MIT |
| FLUX.2 \[klein\] 4B (Black Forest Labs): [nvfp4 build](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-nvfp4) on RTX 50-series, [fp8 build](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8) on RTX 40-series, bf16 build (Comfy-Org repack of `flux-2-klein-4b.safetensors`) on older cards | reference pictures for Prompt to 3D | Apache-2.0 |
| Qwen3-4B text encoder (Alibaba): fp4 build (RTX 50) or bf16 build (older cards) in [Comfy-Org](https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b) | prompt encoding | Apache-2.0 |
| FLUX.2 VAE, same repository | image decoding | Apache-2.0 |

Deliberately **not** used: BRIA RMBG-2.0 (CC BY-NC; ComfyUI's template uses MIT BiRefNet instead), FLUX.2 klein 9B and
other non-commercial FLUX weights, the Tencent Hunyuan3D models (Tencent Hunyuan Community License, which excludes
the EU, UK and South Korea, forbids using outputs to train other AI models and has other restrictions), Qwen-Image 2.1 (research licence, non-commercial),
and the human-specific research models that were evaluated and rejected (HumanNOVA: no licence file, needs SMPL which is non-commercial; PSHuman: over 40 GB of VRAM; Era3D: AGPL-3.0). See [docs/MODELS.md](https://github.com/arashsajjadi/Local3D/blob/main/docs/MODELS.md).

Outputs: generated meshes and pictures are yours to use, subject to the licenses of the models that produced them
(all of the models Local3D downloads allow commercial use of outputs at the time of writing; DINOv3's terms apply
to the model, so read them if you plan commercial use).

## 4. Build tools

The installer is built with [Inno Setup](https://jrsoftware.org/isinfo.php) (Jordan Russell and Martijn Laan; its
license permits distributing the generated setup program). The launcher is compiled with the C# compiler that ships
with Windows. No code from either is copied into this repository.
