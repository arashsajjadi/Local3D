# Contributing

Thanks for helping. Local3D is deliberately small: it should stay a thin layer over official ComfyUI. Before adding
code, ask whether ComfyUI Core, an official template or an official model repository already does it. See
[docs/ARCHITECTURE_DECISION.md](docs/ARCHITECTURE_DECISION.md) for the rule we apply.

## What you need

* Windows 10/11 x64 and an NVIDIA GPU to *run* the apps (RTX 20-series or newer; developed on an RTX 5080).
* Python 3.10+ for the scripts and tests (standard library only, plus Pillow/numpy for `evaluate_samples.py`).
* Nothing else to *change* workflows, docs or Python: `python scripts/validate.py` and the unit tests need no GPU.
  The launcher is compiled with the C# compiler that ships with Windows; the installer needs
  [Inno Setup 6.7+](https://jrsoftware.org/isinfo.php) (CI has it).

```
git clone https://github.com/arashsajjadi/Local3D
cd Local3D
python scripts/validate.py                 # one command: checks everything below
python -m unittest discover -s tests       # unit tests
```

## Layout

| Path | What it is |
| --- | --- |
| `local3d_pack/` | The content ComfyUI loads: `example_workflows/*.app.json` (generated), `variants/` (per-GPU klein builds, generated), an `__init__.py` with no nodes |
| `workflows/upstream/` | Official templates, vendored **unchanged**. Never edit them by hand |
| `scripts/build_workflows.py` | Generates the apps from the upstream templates and `data/presets.json` |
| `scripts/provision_models.py` | Hash-verified model downloads (wraps `huggingface_hub`) |
| `scripts/validate.py` | Repository checks (also run by CI) |
| `scripts/bench_presets.py`, `evaluate_samples.py` | Measure presets / run the evaluation set against a running server |
| `data/` | Single sources of truth: `models.json` (files, hashes), `runtime.json` (pinned ComfyUI), `presets.json`, `frontend-settings.json`, `core_node_types.json` |
| `launcher/Local3D.cs`, `installer/` | The Windows launcher and the installer |
| `docs/`, `tests/` | Documentation and unit tests |

**Never hand-edit a generated app.** Change `scripts/build_workflows.py` or `data/presets.json`, run
`python scripts/build_workflows.py`, and commit the result. `validate.py` (and CI) fail if they disagree.

## Running the apps while you develop

1. Install Local3D once (or let `Local3D.exe` bootstrap the runtime); you now have `runtime\ComfyUI_windows_portable`.
2. Link the pack into the engine's workspace so edits are live (PowerShell):
   `New-Item -ItemType Junction -Path <workspace>\custom_nodes\local3d_pack -Target <repo>\local3d_pack`
3. Start the engine the way the launcher does (see *Launch flags* in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)), then open
   `http://127.0.0.1:<port>/?template=Local3D_Image_to_3D.app&source=local3d_pack&mode=linear`.

Useful environment variables for the launcher: `LOCAL3D_DATA_DIR`, `LOCAL3D_MODELS_DIR`, `LOCAL3D_OUTPUT_DIR`,
`LOCAL3D_ENGINE_ARGS` (extra ComfyUI flags), `LOCAL3D_BROWSER_ARGS` (e.g. `--remote-debugging-port=9333`), and the
`--yes` switch to accept every consent dialog (unattended runs).

### Capturing an app's API prompt (for the benchmark tools)

`bench_presets.py` and `evaluate_samples.py` replay an app through the HTTP API. Open the app in a browser, then run in the
page console and POST the result to the server, e.g. save `(await app.graphToPrompt()).output` as `{"output": ...}` JSON.
Titles of the Model / Quality / Seed nodes are how the tools find the controls, so keep them.

## How to add a model or a workflow

1. **A new open model that ships in ComfyUI Core:** add its files to `data/models.json` (use real sizes and SHA-256 from
   Hugging Face, pin the commit `revision`), build the graph from an *official template* (vendor it under
   `workflows/upstream/` with its provenance in that folder's README), extend `scripts/build_workflows.py`, regenerate,
   then run the app for real. Update [docs/MODELS.md](docs/MODELS.md) and `THIRD_PARTY_NOTICES.md` (license!).
2. **Changing quality presets:** edit `data/presets.json`, regenerate, run `scripts/bench_presets.py` and put the new
   measurements in [docs/QUALITY.md](docs/QUALITY.md). Do not invent values: derive them from upstream defaults and measure.
3. **Bumping ComfyUI:** see *Upgrading the runtime* in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
4. **Custom nodes are not accepted** for the shipped apps. If Core cannot do something, document the limitation (with
   the upstream issue) first; a tiny isolated extension is the last resort.

## Rules for changes

* **Run `python scripts/validate.py` and the unit tests before opening a pull request.** CI runs both.
* Test what you change by *running* it. Many bugs here only show up in the real app (muted pass-through nodes, list
  literals in Math nodes, inverted masks were all found that way).
* Keep user-facing text in plain language and use the product's words consistently: **Run** (the App Mode button),
  **Quality**, **Model**, **Background**, **Seed**.
* Don't commit weights, generated meshes, private pictures, logs, or machine-specific paths. The validator rejects them.
* No telemetry, accounts or cloud calls, ever, without an explicit opt-in design discussion first.

## Commits and pull requests

[Conventional Commits](https://www.conventionalcommits.org/), one understandable step per commit:
`feat:`, `fix:`, `docs:`, `test:`, `build:`, `ci:`, `chore:`, `ux:`. Example: `fix: preserve source image after failed generation`.
Describe *why* and how you tested it. Update `CHANGELOG.md` for user-visible changes.
