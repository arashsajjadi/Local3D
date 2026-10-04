# Changelog

All notable user-visible changes. The Git history has the engineering detail.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/arashsajjadi/Local3D/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/arashsajjadi/Local3D/releases/tag/v0.1.1
[0.1.0]: https://github.com/arashsajjadi/Local3D/releases/tag/v0.1.0
