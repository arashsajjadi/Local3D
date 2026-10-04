# Third-party notices

Local3D itself is MIT-licensed (see [LICENSE](LICENSE)). That license covers **only the files in this repository**.
Local3D runs, but does not contain or modify, the software and models below. Each has its own license, which applies
to you when you download and use it. This is a good-faith summary, not legal advice; the linked originals are authoritative.

Local3D is an independent project. It is **not affiliated with or endorsed by** Comfy Org, Microsoft, Tencent, Meta,
Black Forest Labs, Alibaba, NVIDIA or anyone else listed here.

## 1. Content derived from upstream (included in this repository)

| Component | What we include | License |
| --- | --- | --- |
| [Comfy-Org/workflow_templates](https://github.com/Comfy-Org/workflow_templates) | `workflows/upstream/*.json` are unmodified copies of two official templates; `local3d_pack/example_workflows/*.app.json` are generated from them by `scripts/build_workflows.py` | MIT, see below |

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
this project; they contain no third-party artwork. Sample input images used by some upstream templates are not redistributed.

## 2. Runtime downloaded on first start (not included in this repository or the installer)

| Component | Source | License |
| --- | --- | --- |
| ComfyUI (server and core nodes) | [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI), official Windows portable release, pinned in `data/runtime.json`, checksum-verified | GPL-3.0 |
| ComfyUI frontend (the App Mode UI, 3D viewer) | bundled in the portable build ([Comfy-Org/ComfyUI_frontend](https://github.com/Comfy-Org/ComfyUI_frontend)) | GPL-3.0 |
| comfy-aimdo, comfy-kitchen | bundled in the portable build | GPL-3.0 / see package |
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
| DINOv3 ViT-L image encoder (Meta), repacked in [Comfy-Org/Pixal3D](https://huggingface.co/Comfy-Org/Pixal3D) | conditioning for both 3D models | **Meta DINOv3 License (custom, not MIT).** Read it at <https://ai.meta.com/resources/models-and-libraries/dinov3-license/>. It includes redistribution, trade-control and military end-use terms. Local3D downloads the file for you directly from Hugging Face and does not redistribute it |
| [BiRefNet](https://huggingface.co/ZhengPeng7/BiRefNet) (Peng Zheng et al.); repack: [Comfy-Org/BiRefNet](https://huggingface.co/Comfy-Org/BiRefNet) | background removal | MIT |
| [MoGe-2](https://github.com/microsoft/MoGe) (Microsoft); repack: [Comfy-Org/MoGe](https://huggingface.co/Comfy-Org/MoGe) | camera / field-of-view estimation | MIT (code), includes DINOv2 code under Apache-2.0 |
| [FLUX.2 \[klein\] 4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-nvfp4) (Black Forest Labs), nvfp4 build | reference pictures for Prompt to 3D | Apache-2.0 |
| Qwen3-4B text encoder (Alibaba), fp4 build in [Comfy-Org](https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b) | prompt encoding | Apache-2.0 |
| FLUX.2 VAE, same repository | image decoding | Apache-2.0 |

Deliberately **not** used: BRIA RMBG-2.0 (CC BY-NC; ComfyUI's template uses MIT BiRefNet instead), FLUX.2 klein 9B and
other non-commercial FLUX weights, and the Tencent Hunyuan3D models (Tencent Hunyuan Community License, which excludes
the EU, UK and South Korea and has other restrictions). See [docs/MODELS.md](docs/MODELS.md).

Outputs: generated meshes and pictures are yours to use, subject to the licenses of the models that produced them
(all of the models Local3D downloads allow commercial use of outputs at the time of writing; DINOv3's terms apply
to the model, so read them if you plan commercial use).

## 4. Build tools

The installer is built with [Inno Setup](https://jrsoftware.org/isinfo.php) (Jordan Russell and Martijn Laan; its
license permits distributing the generated setup program). The launcher is compiled with the C# compiler that ships
with Windows. No code from either is copied into this repository.
