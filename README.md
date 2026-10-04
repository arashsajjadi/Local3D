# Local3D

**Turn a photo or a text prompt into a textured 3D model, on your own NVIDIA GPU, offline.**

- **Local and private.** After a one-time download of the models, your pictures, prompts and 3D models never leave your PC. No account, no Local3D telemetry.
- **Simple.** Drop a picture (or type a prompt), pick a quality, press **Run**. No node graph, no Python, no model folders.
- **Open models.** Pixal3D and TRELLIS.2 build the 3D model; FLUX.2 klein draws reference pictures. All run through official ComfyUI.
- **Real assets.** A UV-unwrapped mesh with PBR (realistic material) textures (base colour, metallic, roughness, normal, occlusion) in one `.glb` file, a standard 3D format that opens in Blender, game engines and most viewers.

![Local3D turning a picture of a robot into a 3D model: removing the background, building the shape, baking textures, then the finished model in the viewer](docs/images/demo.gif)

## Quick start

Windows 10/11 and an NVIDIA RTX 20-series or newer graphics card (12 GB+ recommended). Developed and tested on Windows 11 with an RTX 5080 only; other setups should work but are untested. About 26 GB of disk space on an RTX 50-series card (up to 36 GB on older cards).

1. Download **Local3D-Setup-0.1.2.exe** from the [latest release](https://github.com/arashsajjadi/Local3D/releases/latest).
   Windows SmartScreen will warn because the installer is not code-signed yet: *More info* > *Run anyway*.
2. Install it, then start **Local3D** from the Start menu.
3. On first start Local3D asks before each download: **OK** for the ComfyUI engine (2 GB, the open-source tool that runs the models), then **Download** for the AI models (15 GB, plus an optional 7 to 16 GB for prompts).
   It resumes if interrupted, and everything is checked against checksums.
4. A sample picture is ready: press **Run**. Or drop your own picture of **one object, fully in frame**. For text prompts, use the *Apps* icon in the left bar (hover over the icons to see their names) or *Start > Local3D tools*.
5. Turn the finished model around in the viewer. It is saved automatically as a `.glb` in `Documents\Local3D\models`, and the download button above the viewer saves a copy anywhere you like. Wait for the viewer to show the result before closing the window: closing it quits Local3D and cancels a model that is still being made.

More detail: [docs/INSTALL.md](docs/INSTALL.md). Something wrong? [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

![The Local3D app, ready to run](docs/images/app-image-ready.png)

## What you get

| App | Use it to | Time (RTX 5080, models already loaded) |
| --- | --- | --- |
| **Image to 3D** | turn one picture into a textured 3D model | Fast 38 s, **Balanced 81 s**, Maximum 111 s |
| **Prompt to 3D** | describe an object; Local3D draws a reference picture, then builds the model | Fast about 50 s, Balanced 100 to 190 s |
| **Reference Pictures** | make 1, 2 or 4 candidate pictures from a prompt, then pick the best for *Image to 3D* | about 6 s for four |

Controls: **Model** (Auto = Pixal3D, or TRELLIS.2), **Quality** (Fast, Balanced, Maximum), **Output** (High fidelity, or Game asset with
about 30k triangles, for games and apps), **Background** (Auto, Remove, Keep your own transparent PNG) and **Seed**. Times were measured on one machine, not promised: the first row is Pixal3D with models already loaded; TRELLIS.2 and the first run after starting are slower (see [docs/QUALITY.md](docs/QUALITY.md)).

Single-picture 3D *estimates* the sides it cannot see. Show the whole object on a simple background, and treat the back as a good guess.

## Supported models

| Model | Role | License | Download |
| --- | --- | --- | --- |
| [Pixal3D](https://huggingface.co/TencentARC/Pixal3D) | image to 3D, default | MIT | in the 15 GB pack |
| [TRELLIS.2](https://github.com/microsoft/TRELLIS.2) | image to 3D, alternative for intricate or thin objects | MIT | in the 15 GB pack |
| [FLUX.2 klein 4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-nvfp4) | reference pictures for prompts | Apache-2.0 | optional, 6.6 to 16 GB by GPU |

Model licenses differ from this project's MIT license; the DINOv3 encoder both 3D models need is under Meta's own license.
See [docs/MODELS.md](docs/MODELS.md) (including why Hunyuan3D is not in v0.1.0) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Example results

Eight objects chosen to stress different things, each through **both models at Balanced**: every run, including the weak ones.
Left to right: the reference picture, Pixal3D, TRELLIS.2.

![Toolbox, pocket watch, fox, chair: reference, Pixal3D, TRELLIS.2](docs/images/examples-1.jpg)
![Basket, teapot, hat, robot: reference, Pixal3D, TRELLIS.2](docs/images/examples-2.jpg)

* Thin spindles, open tops, small handles and fine gears are kept by both models.
* **Shiny chrome is the weak spot** (see the teapot): reflections turn into blotchy texture.
* Pixal3D stays closer to the picture's colours; TRELLIS.2 sometimes drifts (the basket, the robot's visor).
* One of the 16 runs failed: TRELLIS.2 at Balanced ran out of GPU memory on the knitted hat while other programs held about 5 GB of the card.
  Local3D says what to do in plain words (lower the Quality or switch Model), and your settings stay put.

Details, timings and how the presets were chosen: [docs/QUALITY.md](docs/QUALITY.md).


## Privacy

Generation runs on your PC. Pictures, prompts and meshes are not uploaded anywhere, there is no telemetry, and no account is needed.
The internet is used only for the first-run downloads (the ComfyUI runtime from GitHub, models from Hugging Face). After
that, generation works offline. The diagnostics summary contains versions and hardware only. The app window is Microsoft Edge,
a separate program: its own background connections to Microsoft follow your Windows and Edge privacy settings and are not
controlled by Local3D (Local3D blocks known telemetry hosts inside that window and runs it with its own separate profile).

## How it works

Local3D is a thin layer over official, unmodified [ComfyUI](https://github.com/Comfy-Org/ComfyUI): a tiny launcher starts
it privately on your PC, a set of ComfyUI *App Mode* apps (built only from Comfy Core nodes) provides the simple screens, and the
official 3D nodes do the work. Experts can switch any app to the full graph. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[why ComfyUI rather than LocalAI or Comfy Desktop](docs/ARCHITECTURE_DECISION.md).

## For developers

```
git clone https://github.com/arashsajjadi/Local3D
cd Local3D
python scripts/validate.py && python -m unittest discover -s tests
```
See [CONTRIBUTING.md](CONTRIBUTING.md). Independent project, not affiliated with Comfy Org, Microsoft, Tencent, Meta or Black Forest Labs.
License: [MIT](LICENSE) for this repository's files; runtime and models have their own licenses.

If Local3D is useful to you, consider starring the repository.
