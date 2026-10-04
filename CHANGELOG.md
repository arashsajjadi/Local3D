# Changelog

All notable user-visible changes. The Git history has the engineering detail.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-04

First public version.

### Added
- **Image to 3D** app: drop a picture, choose Model (Auto = Pixal3D, or TRELLIS.2), Quality (Fast, Balanced, Maximum)
  and Background (Auto, Remove, Keep), press Run, inspect the textured PBR model, export GLB.
- **Prompt to 3D** app: prompt, reference picture (FLUX.2 klein 4B), 3D model in one run, with an optional
  "3D-friendly reference" framing.
- **Reference Pictures** app: 1, 2 or 4 candidate pictures from a prompt in seconds, to pick before spending minutes on 3D.
- Windows installer (2 MB) with a Start Menu entry; the ComfyUI runtime and models are downloaded on first start,
  with checksums, resume, disk-space checks and a choice of folder.
- GPU-aware FLUX.2 klein weights: nvfp4 (RTX 50), fp8 (RTX 40), bf16 (older).
- Diagnostics summary that is safe to share (versions, GPU, installed model files).

### Notes
- Built on ComfyUI 0.38.0 (Comfy Core nodes only, no custom nodes). Tested on an NVIDIA RTX 5080 only.
- Hunyuan3D and multi-view Pixal3D are not included (see docs/MODELS.md).
- The installer is not code-signed; Windows SmartScreen will warn.

[Unreleased]: https://github.com/arashsajjadi/Local3D/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/arashsajjadi/Local3D/releases/tag/v0.1.0
