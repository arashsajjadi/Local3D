# Changelog

All notable user-visible changes. The Git history has the engineering detail.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-04

People and characters now come out much better, and *Image to 3D* tells you what it decided and why. The cause of the problem and
the evidence for the fix are in [docs/CHARACTER_FAILURE_ANALYSIS.md](docs/CHARACTER_FAILURE_ANALYSIS.md) and
[docs/CHARACTER_ROUTING_DECISION.md](docs/CHARACTER_ROUTING_DECISION.md).

### Added
- **Subject** control in *Image to 3D*: **Auto** (recommended), **Object**, **Character bust** or **Complex** (thin or open shapes, uses TRELLIS.2).
  Two small detectors that run locally (a person detector and a face detector, about 2 seconds) look at your picture first.
- **Character bust** workflow: for a head-and-shoulders or half-length picture of a person or character, Local3D cuts the picture
  below the chest *before* removing the background, so the face and hands reach the model at a higher resolution. Auto does this only when it
  makes the subject larger for the model (tall or tightly framed pictures; in a square picture the cut would change nothing and cost time and
  memory, so the picture stays whole). On the test picture (a comic officer saluting) the hand now reaches the visor with a thumb and stepped
  fingertips instead of a flat paddle at the ear, and the face, glasses frames, cap braid and epaulettes come out as shapes; fingers can still be partly fused.
- **Subject report**, written under the prepared picture in the row under the result, in plain words: what was detected (with scores), what was chosen and by whom, how the
  picture was framed, and that the back and far side are inferred. When Auto is not sure (a person without a clear face, a face
  without a person such as a toy) it keeps the plain Object workflow and says so; one click on *Character bust* overrules it.
- **Character from views** app (*Start > Local3D tools*): build a model from two or four **real** views of the same subject (front, left, back,
  right) with Pixal3D's multi-view mode, so the back and the far side are measured instead of guessed.
  It needs one optional 5.6 GB model that is downloaded only when you first open the app.
- The download dialog lists every model pack that is missing with its size, marks an update to an installed pack, and lets each optional pack be
  declined separately and offered again later (*Start > Local3D tools > Download more models*).
- Developer tools: `scripts/check_routing.py` (what Auto decides for the evaluation pictures, in seconds), `scripts/mesh_report.py`
  (triangles, components, open edges, watertightness of a GLB), `scripts/render_glb_views.py`, eleven evaluation pictures in `assets/eval/`.

### Changed
- The required model pack grows by 130 MB (the two detectors). Existing installs are asked before anything is downloaded.
- *Object* pictures take the same path as in 0.1.x; the extra look at the picture costs about two seconds. A Character bust takes about 1.5 to 2 times as long
  as the whole picture and can use up to about 1.5 GB more graphics memory, because it fills more of the model's input.

### Fixed
- On a fresh install the very first start could stop with "the process cannot access the file" while finishing the unpacking of the runtime (antivirus software
  briefly holding its temporary folder). That step now retries and never fails a start over a leftover folder.

### Notes
- Full-length figures stay on the Object workflow (their faces are too small to crop to); choose *Character bust* to crop to the upper body yourself.
- Not added, with reasons: generated extra views (measured worse than a good single view), Hunyuan3D-2mv, HumanNOVA, PSHuman, DiGS-Avatar,
  Unique3D / Wonder3D / Era3D, SAM 3D Body. A 3D-print mode was tried and not shipped: the clean-up steps ComfyUI's core nodes offer made the meshes worse, not watertight.

## [0.1.2] - 2026-10-04

### Fixed
- In about one launch in ten the Local3D launcher kept running (and kept the next start from opening) after the app window was
  closed, because Edge leaves a background process of its profile behind for a moment. Local3D now treats a visible app
  window as "open", and stops any background Edge of its own profile when it shuts down.

## [0.1.1] - 2026-10-04

Fixes a start-up failure in 0.1.0: on some PCs the app window opened and stayed on the dark ComfyUI splash forever.

### Fixed
- **Stuck on the ComfyUI splash.** Edge sometimes hands the app window to another process and the one Local3D started exits
  at once; 0.1.0 took that for "window closed" and shut the engine down, leaving a window with nothing to connect to.
  Local3D now finds its window by its own private browser profile, closes leftovers of that profile before opening a new
  window, and its window closes with Local3D even after a crash.
- Start-up can no longer wait forever: the interface must report ready within 90 seconds, otherwise a dialog offers
  **Retry**, **Repair interface** (resets only Local3D's own browser data), **Open diagnostics** and **Quit**.

## [0.1.0] - 2026-10-04

First public version.

### Added
- **Image to 3D** app: drop a picture, choose Model (Auto = Pixal3D, or TRELLIS.2), Quality (Fast, Balanced, Maximum),
  Output (High fidelity, or Game asset with about 30k triangles) and Background (Auto, Remove, Keep), press Run, inspect the textured PBR model, export GLB.
- **Prompt to 3D** app: prompt, reference picture (FLUX.2 klein 4B), 3D model in one run, with an optional
  "3D-friendly reference" framing.
- **Reference Pictures** app: 1, 2 or 4 candidate pictures from a prompt in seconds, to pick before spending minutes on 3D.
- Windows installer (2 MB) with a Start Menu entry; the ComfyUI runtime and models are downloaded on first start,
  with checksums, resume, disk-space checks and a choice of folder.
- GPU-aware FLUX.2 klein weights: nvfp4 (RTX 50), fp8 (RTX 40), bf16 (older).
- Diagnostics summary that is safe to share (versions, GPU, installed model files).
- Plain-language message when the GPU runs out of memory, and an uninstaller that never deletes your models without a separate question.

### Notes
- Built on ComfyUI 0.38.0 (Comfy Core nodes only, no custom nodes). Tested on an NVIDIA RTX 5080 only.
- Hunyuan3D and multi-view Pixal3D are not included (see docs/MODELS.md).
- The installer is not code-signed; Windows SmartScreen will warn.

[Unreleased]: https://github.com/arashsajjadi/Local3D/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/arashsajjadi/Local3D/releases/tag/v0.2.0
[0.1.2]: https://github.com/arashsajjadi/Local3D/releases/tag/v0.1.2
[0.1.1]: https://github.com/arashsajjadi/Local3D/releases/tag/v0.1.1
[0.1.0]: https://github.com/arashsajjadi/Local3D/releases/tag/v0.1.0
