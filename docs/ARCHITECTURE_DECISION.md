# Architecture decision: which runtime does Local3D stand on?

- **Status:** accepted
- **Evidence date:** 2026-10-04 (every upstream fact below was read from a primary source on that day and
  re-checked by two independent reviewers; items that are inference rather than observation are marked *(inferred)*)
- **Decision:** build on the **unmodified official ComfyUI Windows portable build**, ship Local3D as a
  **data-only content pack (workflows + App Mode apps)**, and add one **very small native launcher/installer layer**.
  Do not build on LocalAI. Do not build on Comfy Desktop.

## 1. What we need

A Windows user should go *Start Menu → Local3D → drop an image (or type a prompt) → Generate → inspect → export GLB*,
without ever seeing a node graph, a terminal, a Python environment or a model folder. Everything heavy
(inference, 3D post-processing, viewer, queue, history, model metadata) should come from mature upstream code.

## 2. The three candidates

| Option | One-line description |
| --- | --- |
| **A. LocalAI** | `mudler/LocalAI` as runtime and UI (its `/3d/generations` API, `trellis2cpp` backend, built-in WebGL viewer). |
| **B. Comfy Desktop + App Mode** | Official Comfy Desktop app hosting our workflows/apps as templates. |
| **C. Owned ComfyUI portable + pack + thin launcher** *(chosen)* | Official ComfyUI portable (pinned release, unmodified) started by a small launcher, showing our App Mode apps in a chromeless Edge window; content shipped as a custom-node-folder pack. |

## 3. Decision table

Legend: ✅ works today · ⚠️ partial / needs work · ❌ not available · ❓ unverified

| Criterion | A. LocalAI v4.11 | B. Comfy Desktop 1.1.6 | C. ComfyUI portable v0.38.0 + pack + launcher |
| --- | --- | --- | --- |
| Native Windows install | ❌ no Windows asset in v4.8–v4.11 releases; Docker Desktop/WSL2 only. Native-Windows PR #11429 is open, CPU/Vulkan only, no CUDA | ✅ NSIS installer (per-user) | ✅ official 7z portable (CUDA 13.0, Python 3.13, ~2 GB); we add a small installer |
| Steps for a novice | ❌ ~8, several in a terminal (Docker Desktop, `wsl --update`, `docker run --gpus all …`) | ⚠️ install + find our template in the Templates browser | ✅ install Local3D → click shortcut (runtime/models fetched on first run) |
| Start Menu → opens *our* app directly | ❌ | ❌ no CLI args, no protocol handler, single-instance focus-only; can only open built-in templates | ✅ launcher passes the app deep link (`/?template=…&source=…&mode=linear`) |
| Image → 3D | ✅ TRELLIS.2 only (f16 GGUF, 512/1024 cascade) | ✅ | ✅ |
| Pixal3D | ❌ only a *draft*, bot-authored PR #12319 | ✅ if ComfyUI ≥ 0.34 | ✅ native core nodes since ComfyUI 0.34.0 |
| TRELLIS.2 | ✅ | ✅ | ✅ native core nodes, 1536 cascade, BiRefNet matting |
| Hunyuan3D | ❌ no backend or PR | ⚠️ shape-only (core) | ⚠️ shape-only (core); license limits (see `MODELS.md`) |
| PBR GLB output | ⚠️ dense vertex colours + non-standard attribute by default; UV textures only after the CGAL print-remesh step | ✅ UV unwrap + base colour/metallic/roughness/normal/AO bakes | ✅ same |
| Prompt → 3D | ❌ image-conditioned only | ⚠️ compose ourselves | ✅ compose text-to-image → 3D in one app |
| 3D viewer | ✅ custom WebGL2 (orbit/pan/zoom/wireframe) | ✅ ComfyUI viewer (three.js r184) | ✅ same; no named front/back/top views in either *(gap, see §6)* |
| Progress / cancel | ❌ spinner + elapsed time, no cancel | ✅ node/step progress, Interrupt | ✅ |
| Model download | ✅ gallery with SHA-256, `.partial` resume | ⚠️ missing-model download lives in the graph *Errors* tab, not in App Mode; open downloader bugs | ⚠️ same upstream flow as fallback + our small, hash-pinned first-run provisioning (§5) |
| Output history | ⚠️ browser-local, 20 entries | ✅ | ✅ |
| Consumer GPU / RTX 50 (Blackwell) | ✅ sm_120a in ggml fork, CUDA 12.8/13 images (under WSL2) | ✅ | ✅ (torch cu130, aimdo dynamic VRAM) |
| Licensing of the host | MIT | **AGPL-3.0-or-later / commercial**, EULA still says MIT (issue #1580) | GPL-3.0, run unmodified as a separate process |
| Telemetry of the host | none known | **forced EULA; telemetry and beta default ON** | none observed in the portable build we launch (measured; see *Launch flags* in `ARCHITECTURE.md`) |
| Process cleanup | ❌ containers | ⚠️ new Desktop tracks trees; legacy leaves orphans (#1595) | ✅ launcher owns the process tree via a Windows Job Object |
| Custom code we must write | Windows port of server + trellis2cpp + Pixal3D/Hunyuan backends (Go/C++), or a fork | pack only, but cannot be launched into | pack (data) + a small launcher (about 1,200 lines as built; estimated at ~150 before implementation) + installer script |
| Maintainability / churn | high churn (minor releases every 10–38 days) | high churn (several releases/week) | ComfyUI ships ~every 6.5 days → we **pin one tested release** and bump deliberately |
| Ease of contribution | Go/C++/React monorepo | content only | content only (JSON, docs, PowerShell) |
| Future extensibility | new backends = new gRPC backends | new templates | new template/app JSON files; any new core node is usable |

## 4. Why not A (LocalAI)

Verified blockers, not preferences:

1. **No native Windows build.** No v4.8–v4.11 release carries a Windows asset; backends are Linux OCI images started
   through a shell script and loaded with `dlopen`. The only route is Docker Desktop + WSL2.
2. **Its 3D feature set trails ComfyUI's** for the same TRELLIS.2 weights: a single backend, no Pixal3D or Hunyuan3D,
   no BiRefNet matting, no cancel button, no per-step progress, GLB-only export, history capped at 20 browser-local entries.
3. **A Windows port is more code than this whole project**, and a fork would turn Local3D into a permanent large fork.

*Re-evaluation trigger:* revisit if **both** (a) native-Windows PR #11429 merges with a CUDA path **and** (b) a Windows
`trellis2cpp` build exists. Ideas worth borrowing (not depending on): hash-pinned `.partial`+Range downloads and
hardware-aware model variants.

## 5. Why not B (Comfy Desktop), and what C adds on top of ComfyUI

Comfy Desktop is the right host for a *ComfyUI user*; it is the wrong host for a *product*:

- It cannot be launched into a specific app (no argv, no protocol handler, no file association; single-instance lock only focuses).
  A shortcut named "Local3D" could only start generic Desktop.
- Custom packs show up as ordinary *Node graph* templates under *Extensions* and never in the *Apps* filter.
- Its license changed to AGPL-3.0-or-later/commercial on 2026-07-30, first run forces EULA acceptance, telemetry defaults on
  — at odds with a "local, no telemetry" promise we cannot control from outside.
- The Desktop installed on the development machine (0.8.2, ComfyUI 0.12.2) predates native Pixal3D/TRELLIS.2 and is
  frozen; it can be replaced in place by auto-update, so it is a moving target.

**C therefore owns the process, not the code.** Everything below is *unmodified upstream*:

| Layer | Source | Local3D adds |
| --- | --- | --- |
| Runtime, frontend, 3D nodes, queue, history, viewer, App Mode | Official `ComfyUI_windows_portable_nvidia.7z` (pinned tag, SHA-256 verified) | nothing |
| Content | `local3d_pack/` (custom-node folder containing only `__init__.py` + JSON) | Image→3D and Prompt→3D apps, quality presets, notes |
| Start / stop | — | launcher: picks a free port, starts ComfyUI with safe flags, waits for readiness, opens the app in a chromeless Edge window, tears the process tree down when the window closes |
| Install | — | Inno Setup (per-user) installer; Start Menu shortcut with icon |
| Models | Official HF files, same `properties.models` metadata ComfyUI itself uses | first-run provisioning script with resume + SHA-256 (justified in §6) |

The pack also works in **any** ComfyUI ≥ 0.35 (including Comfy Desktop) by copying one folder — the launcher is optional
for experts, which keeps the "open the real graph" escape hatch.

## 6. Limitations of App Mode that the design works around (verified, not assumed)

| Limitation (frontend 1.53.x) | Consequence for Local3D |
| --- | --- |
| One **Run** button executes the whole graph; no approval gate, no partial execution in the app UI | Outcome: two apps. *Prompt to 3D* runs everything; *Reference Pictures* makes candidates first and the person picks one in *Image to 3D* (see "Why Reference pictures is a separate app" in `ARCHITECTURE.md`) |
| App Mode UI has no named Front/Back/Top views | document the axis gizmo + Fit/Center; do not build a custom ViewCube |
| Missing-model resolution is in the graph *Errors* tab, only for `huggingface.co`/civitai URLs and `.safetensors`-type files | embed `properties.models` metadata (works as fallback) **and** provision all weights ourselves on first run |
| 3D result renders only from nodes that emit a `3d` result (`SaveGLB`, `Save3DAdvanced`) | the app output is a Save node, never a Preview node |
| Mesh export from core is GLB only | GLB is the one exposed format (OBJ/STL/FBX export exists in the viewer's browser-side export menu) |
| "Save As" on an App empties its inputs (#19356, #14838) | apps are authored once and shipped as files; legacy-compatible `linearData` tuples |

## 7. Pinned upstream versions (tested set)

See `docs/ARCHITECTURE.md` for the exact tested set; the decision-time facts were: ComfyUI **v0.38.0** (2026-09-29, frontend
1.53.6, workflow templates 0.11.70, comfy-kitchen 0.2.36, comfy-aimdo 0.5.5). v0.38.1/v0.38.2 contain only partner-API nodes
and template bumps (no 3D changes), have no portable archive, and are not worth the divergence. Minimum for any other
ComfyUI: **0.35.0**.

## 8. Known risks accepted with this decision

1. **VRAM fit on a card shared with other apps** (the development GPU has ~5 GB free at idle). Template defaults ask for
   8–9 GiB in the heaviest stages; the Fast/Balanced presets exist for this reason and are measured, not guessed.
2. **Dynamic-VRAM / INT8 stability on Windows + Blackwell** has non-3D failure reports. Mitigation: hard version pin,
   documented contingency flags, never enabling the flags known to corrupt TRELLIS.2 (`--use-ck-attention`).
3. **Licensing:** ComfyUI is GPL-3.0 and is downloaded and run as a separate unmodified process, never copied into this MIT
   repository; the pack contains no ComfyUI code. DINOv3 (mandatory encoder) is under Meta's DINOv3 License, not MIT.
   See `THIRD_PARTY_NOTICES.md` and `MODELS.md`. This is engineering analysis, not legal advice.
4. **Unsigned installer** → SmartScreen warning; Windows offers no silent Pin-to-Start for unpackaged apps, so we create
   the Start Menu entry and tell the user how to pin.

## 9. Sources

Primary sources read on 2026-10-04 (non-exhaustive): `Comfy-Org/ComfyUI` (releases, `comfy_extras/nodes_trellis2.py`,
`nodes_mesh_postprocess.py`, `nodes_save_3d.py`, `comfy/cli_args.py`), `Comfy-Org/ComfyUI_frontend` (App Mode / linear mode,
`useTemplateUrlLoader.ts`), `Comfy-Org/workflow_templates` (`3d_pixal3d_trellis2_image_to_model`), `Comfy-Org/Comfy-Desktop`
(source, LICENSE, e2e deep-link tests), `Comfy-Org/desktop` (archived), `docs.comfy.org`, `mudler/LocalAI` (release assets,
install docs, `backend/go/trellis2cpp`, PRs #10979/#11429/#12319), Hugging Face model repositories of Comfy-Org,
TencentARC, microsoft, black-forest-labs and tencent.
