# Security policy

Local3D runs on your own PC, makes no network connections of its own except the first-run downloads
(GitHub for the ComfyUI runtime, Hugging Face for the model files, both checksum-verified), and has no account or telemetry.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private reporting instead:
[Security > Report a vulnerability](https://github.com/arashsajjadi/Local3D/security/advisories/new).
Include the Local3D version (`Local3D.exe --version`), what you did and what you expected. You will get an answer as soon as
the maintainer can, normally within a few days. This is a spare-time project: there is no bug bounty.

## Scope

In scope: the launcher, the installer, the scripts and the app files in this repository. Out of scope: vulnerabilities in ComfyUI,
PyTorch, the AI models or Microsoft Edge themselves; please report those upstream.

The installer is **not code-signed** in v0.1.0; verify downloads against `SHA256SUMS.txt` and the build-provenance attestation on the release.
