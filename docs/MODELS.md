# Models

Local3D downloads open model files on first start, after asking. Nothing is bundled in the installer or this repository.
All files are pinned to exact Hugging Face revisions and SHA-256 hashes in [`data/models.json`](../data/models.json).

## What gets installed

| Pack | Contents | Download | Needed for |
| --- | --- | --- | --- |
| **Image to 3D** (required) | Pixal3D, TRELLIS.2, shared 3D VAEs, DINOv3 encoder, MoGe-2, BiRefNet, and two small subject detectors (RT-DETR person, MediaPipe face) | **15.3 GB** | *Image to 3D*, *Prompt to 3D* |
| **Prompt to 3D** (optional) | FLUX.2 klein 4B and Qwen3-4B text encoder (nvfp4 + fp4 on RTX 50-series, fp8 + bf16 encoder on RTX 40-series, bf16 on older cards), FLUX.2 VAE | **6.6 GB** (RTX 50) / **12.5 GB** (RTX 40) / **16.1 GB** (older) | *Prompt to 3D*, *Reference Pictures* |
| **Character from views** (optional, asked for only when you open that app) | Pixal3D multi-view model (int8) | **5.6 GB** | *Character from views* |
| ComfyUI runtime (not a model) | official portable build | 2.0 GB (unpacks to ~4.4 GB) | everything |

The default install (runtime, Image to 3D, Prompt to 3D) is about **26 GB** on disk on an RTX 50-series card, up to about 36 GB on older cards;
the *Character from views* model adds 5.6 GB. Both Pixal3D and TRELLIS.2 are
in the required pack because they share about 4.4 GB of files (both VAEs, DINOv3, MoGe-2, BiRefNet): adding TRELLIS.2 to Pixal3D costs only its own 5.3 GB model.
Declined an optional pack? Run *Start > Local3D tools > Download more models* later.
Upgrading from 0.1.x: the two detectors (130 MB) are the only new files in the required pack, and Local3D asks before fetching them.

## The 3D models, honestly

Measured on an NVIDIA RTX 5080 (16 GB, with other programs holding 3 to 10 GB of it), ComfyUI 0.38.0, one 1024 px
picture of a detailed axe, fresh seed per run, models already loaded. One picture on one machine is an indication, not a
benchmark; see [QUALITY.md](QUALITY.md) for the eight-object evaluation.

| | **Pixal3D** (default, "Auto") | **TRELLIS.2** |
| --- | --- | --- |
| Made by / weights license | TencentARC / **MIT** (since 2026-05-20; earlier versions were academic-only) | Microsoft / **MIT** |
| Strength | follows the reference picture closely (shape and fine surface detail) | strong on complex topology, thin structures and open surfaces; its authors target 3D assets with PBR materials |
| Input | one picture | one picture |
| Output here | UV-unwrapped mesh with base colour, metallic, roughness, normal and ambient-occlusion maps, packed in one GLB | same |
| Time (Fast / Balanced / Maximum) | 38 s / 81 s / 111 s | 53 s / 137 s / 145 s |
| GLB size / triangles (Balanced) | 30 MB / 299 k | 30 MB / 295 k |
| Known limits | guesses the hidden back side; may shrink or merge very thin parts | slower here; guesses the hidden back side; can drift on flat or vector artwork (upstream note) |
| Choose it when | you want the result to look like your picture | the object is intricate, thin or has holes and Pixal3D loses parts |

Neither is "better": try the other when a result disappoints. **Auto always means Pixal3D**; Local3D never switches to a
different pipeline behind your back.

Both need the whole object visible in the picture. Single-picture 3D invents the sides it cannot see.

## The subject detectors (Image to 3D)

Before generating, *Image to 3D* looks at the picture with two small detectors that run **locally, in about two seconds**, to decide
whether it shows a person (see [CHARACTER_ROUTING_DECISION.md](CHARACTER_ROUTING_DECISION.md)):

| Detector | Role | Size | Licence |
| --- | --- | --- | --- |
| RT-DETR v4 (X, fp16; Comfy-Org repack of the COCO-trained model) | finds a person | 124 MB | Apache-2.0 weights, MIT repack |
| MediaPipe face landmarker (Comfy-Org repack) | finds a face | 5.4 MB | Apache-2.0 |

They only produce numbers (a score and a box); nothing is generated, uploaded or stored. The *Subject* control overrules them.

## The multi-view model (Character from views)

The optional *Character from views* app feeds two or four **real** views (front, left, back, right of the same subject) to
Pixal3D's multi-view mode, so the back and the far side are measured instead of guessed. It uses a second Pixal3D model
(`pixal3d_multiview_int8_convrot`, 5.6 GB, MIT) that the app asks to download the first time you open it.
The four views must be consistent with each other (same subject, same scale, same lighting): Local3D does not invent them.

## The reference-picture model

**FLUX.2 [klein] 4B** (Black Forest Labs, Apache-2.0) in its distilled 4-step form: the *nvfp4* build on RTX 50-series, *fp8* on RTX 40-series,
*bf16* on older cards.
Chosen because it is permissively licensed, small enough to share a 16 GB card, fast (four candidates in about 6 s here),
and part of ComfyUI Core. Z-Image-Turbo (Apache-2.0) was the runner-up; the larger Qwen-Image models are too big for a
shared 16 GB card, and FLUX.2 klein 9B is non-commercial, so it is not used.

The *3D-friendly* option appends a fixed framing clause asking for a single complete object, small in the frame with a wide empty margin of
plain background, fully visible and not cropped, in a three-quarter view from slightly above on a neutral grey background (wording chosen by
experiment, see [QUALITY.md](QUALITY.md)). Turn it off to send your prompt exactly as typed.

## Where the files go

`models\` under the data folder (default `%LOCALAPPDATA%\Local3D\models`), or the folder you pick in the download dialog
(saved in `settings.json`). Sub-folders follow ComfyUI: `diffusion_models`, `vae`, `clip_vision`, `text_encoders`,
`geometry_estimation`, `background_removal`, `detection`.

**Already have these files from ComfyUI?** Point Local3D at that `models` folder (choose it in the dialog, or set
`modelsDir` in `%LOCALAPPDATA%\Local3D\settings.json`). Files with the same names are checked against the pinned
hashes and kept if they match, so nothing is downloaded twice. Local3D never scans other folders on its own.

Local3D checks the files every time it starts: a missing or changed file is downloaded again, and a half-finished
download resumes where it stopped. *Start > Local3D tools > Diagnostics* shows which model files are installed.

## Not included

* **Hunyuan3D 2.x/2.1.** Local ComfyUI supports only its *shape* stage (a grey mesh, no materials); texturing needs
  compiled CUDA components with no reliable Windows/RTX 50-series build today. Tencent's license also excludes the EU, UK
  and South Korea (including use of outputs), forbids using outputs to improve other AI models and limits large deployments, so it needs an explicit consent flow.
  Hunyuan3D 2.5/3.x are API-only. It can be added later as an optional shape-only pack; until then, the official ComfyUI
  *Hunyuan3D 2.1* template works in any ComfyUI you run yourself. Its multi-view shape model was evaluated on paper only: Pixal3D's multi-view mode does the same job under MIT.
* **Human-specific models** (HumanNOVA, PSHuman, DiGS-Avatar, SAM 3D Body) and **older multi-view generators** (Unique3D, Wonder3D, Era3D):
  too large for 16 GB (PSHuman needs over 40 GB), unclear or restrictive licences (HumanNOVA has no licence file and needs SMPL, which is non-commercial; Era3D is AGPL-3.0),
  Gaussian avatars instead of a GLB (DiGS-Avatar), or sensitive to pose and occlusion. Reasons and sources: [CHARACTER_ROUTING_DECISION.md](CHARACTER_ROUTING_DECISION.md).
* **Generated extra views** (a local image-editing model re-drawing your picture from other angles): measured worse than a good single-view crop, because every view re-draws the details. Not offered.
* **BRIA RMBG-2.0** (non-commercial) and **FLUX.2 klein 9B** (non-commercial): deliberately avoided.

## Licenses

Model licenses are separate from Local3D's MIT license and are listed in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
The one to read: **DINOv3** (Meta's own license, not MIT) is a required encoder for both 3D models.
