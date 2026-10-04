# Troubleshooting

Start with **Start > Local3D tools > Diagnostics > Copy to clipboard**. It lists versions, your GPU and which model
files are installed (no paths, pictures, prompts or tokens), and is exactly what a bug report needs.

Logs (the details behind any friendly message) are in `%LOCALAPPDATA%\Local3D\logs\` (or your data folder):
`launcher.log` (startup and downloads) and `comfyui.log` (the engine).

## Local3D does not start

| What you see | What it means | What to do |
| --- | --- | --- |
| **Windows protected your PC** (SmartScreen) when running the installer | The installer is not code-signed yet | Click *More info*, then *Run anyway*. You can verify the file against `SHA256SUMS.txt` on the release page |
| "needs an NVIDIA graphics card" | No NVIDIA GPU or driver was found | Install the current NVIDIA driver (RTX 20-series or newer). AMD, Intel and Apple GPUs are not supported in v0.1 |
| "Not enough free disk space" | The runtime needs about 7.4 GB free while it unpacks; the models need 15 GB, plus 7 to 16 GB for the optional prompt pack (by GPU), plus 3 GB kept spare | Free space, or choose another folder for the models in the download dialog |
| "Local3D's engine stopped while starting" | The ComfyUI process exited. The technical details show its last lines | Update your NVIDIA driver and start again; if it repeats, see *Engine problems* below |
| Nothing happens after clicking the shortcut | Local3D may already be running or still starting (its window can be behind others) | Click the shortcut again: once the engine is up it opens another window on it; while it is still starting, a message says so |
| `Local3D.exe` is missing, or Windows says it cannot find it, after installing | Antivirus software may have quarantined the unsigned launcher (a common false positive for small unsigned programs) | Windows Security > Virus & threat protection > Protection history > Restore / Allow, or add an exclusion for `%LOCALAPPDATA%\Programs\Local3D`. The source is public and `SHA256SUMS.txt` covers the installer |
| First start takes a minute before the window appears | The engine initialises GPU kernels the very first time | Normal; later starts take a few seconds |

## Downloads

* **Interrupted or failed:** start Local3D again. The runtime and each model file *resume* where they stopped, and finished
  files are never downloaded twice.
* **"A downloaded file failed its checksum and was discarded":** the file was corrupted in transit or changed upstream.
  Start again to fetch it afresh. If it fails repeatedly, open an issue with the diagnostics.
* **Behind a proxy or firewall:** the runtime comes from `github.com`, which redirects to `release-assets.githubusercontent.com`
  (allow `*.githubusercontent.com`); models come from `huggingface.co`, which redirects to Hugging Face's CDN hosts (allow `*.hf.co`).
  The runtime download (curl.exe) reads only the standard `HTTPS_PROXY` / `HTTP_PROXY` environment variables; the model downloader also
  follows a manual proxy set in Windows Settings (not PAC scripts). Setting the environment variables covers both.
* **Offline use:** after the downloads, generation needs no internet (`HF_HUB_OFFLINE` is set for the engine). The one
  thing that needs a connection is the first-run download.
* **Models on another drive:** choose the folder in the download dialog, or edit `modelsDir` in
  `%LOCALAPPDATA%\Local3D\settings.json`.

## While generating

### "Not enough GPU memory" / the run stops with an out-of-memory message

Local3D shares your GPU with every other program (browsers, CAD, games, the desktop itself). Try, in this order:

1. Lower **Quality**: *Maximum* → *Balanced* → *Fast*. The big memory users are the texture bake and the mesh clean-up,
   which the lower presets shrink (see [QUALITY.md](QUALITY.md) for measured times).
2. Close other programs that use the GPU (look at Task Manager > Performance > GPU).
3. Switch **Model** to *Pixal3D* (it was the lighter and faster of the two in our tests).

Local3D never deletes your files or changes your setup after a failure: your picture, prompt and settings stay in the
window, so you can simply lower Quality and press Run again. Upstream reports show 12 GB cards running out of memory at
the old *Maximum* settings; if you have 12 GB or less, start with *Fast* or *Balanced*.

### It is slow

* The **first run** of a session loads several GB of models from disk; the next runs are faster.
* *TRELLIS.2* takes noticeably longer than *Pixal3D* at the same setting; *Maximum* costs more than *Balanced*.
* Drivers matter: update to the current NVIDIA driver.
* Reference pictures (*Prompt to 3D*) take seconds; the 3D stage is the slow part.

### The result looks wrong

* **Part of the object is missing or flat:** show the *whole* object in the picture, with nothing cut off, on a simple
  background. Single-picture 3D must invent every side it cannot see.
* **Background removal cut into the object** (or left a halo): open *Prepared image* output to see what the model saw. Try
  *Background: Remove*, or supply your own cutout as a transparent PNG with *Background: Keep*.
* **Thin parts vanish or merge:** try *Model: TRELLIS.2*, which is better with thin structures and holes in our tests.
* **Mirrors, glass and very dark objects** reconstruct poorly; photograph or generate them differently.
* **A second, hidden surface inside the model** (inner shell) can occur; it is invisible when viewing but matters for
  3D printing. It is a known upstream limitation (ComfyUI issue #16147).
* **Different result each time:** the seed is randomized on every Run. After a run, the Seed box shows the seed that produced the model on
  screen. To repeat it, click the small control button next to Seed, choose *Fixed*, keep that number and press Run again.

### "Media input missing"

The picture file Local3D opened with is not in its input folder (for example you deleted it). Pick or drop another
picture; the Run button warns until a picture is selected.

### Prompt to 3D: the reference picture is poor

Use **Reference Pictures** first: it makes up to four candidates in seconds. Pick the best one in `Documents\Local3D`, then
open *Image to 3D* and choose it (the new pictures are named `Local3D_reference_*`; if you cannot see them in the picture list,
click on the app window and press **R** to refresh the list, or close and reopen the app). Keep the prompt about **one object**; leave *3D-friendly reference* on unless you want
your wording used exactly.

### The model looks faceted or darker than the picture in the viewer

ComfyUI's built-in viewer (*Original* mode) shades the baked normal map more harshly than most programs, so a smooth surface can
look slightly faceted, and shiny metals can look darker. The file itself is fine: its stored normals are smooth. Switch the
viewer's mode to **Clay** or **Normal** to check the shape, or open the `.glb` in Blender or any glTF viewer for a second look.

## Opening and using the result

* **Where is my file?** `Documents\Local3D\models\*.glb`. The viewer's menu can also download or convert it to OBJ, STL
  or FBX. (ComfyUI Core writes GLB; the other formats are converted in the viewer and do not carry all materials. STL has no
  colours or textures at all.)
* **The textures do not show in another program:** the GLB embeds its textures (base colour, metallic/roughness, normal and
  ambient occlusion). Open it in Blender, a glTF viewer, or an online glTF viewer. Windows' built-in previewers vary.
* **A validator complains about a handful of "non-unit-length normals":** about fifty vertices out of hundreds of
  thousands carry degenerate normals from ComfyUI's smoothing step. Renderers renormalise them; nothing is visibly wrong.

## Engine problems (advanced)

If the engine crashes, hangs, or the screen flickers on RTX 50-series cards, try **one** change at a time via the
`LOCAL3D_ENGINE_ARGS` environment variable (set it in *System Properties > Environment Variables*, then restart Local3D):

1. `--disable-pinned-memory`
2. `--disable-async-offload`
3. `--cache-none`
4. `--disable-dynamic-vram` (last resort; upstream says it will be removed)

Do **not** add `--use-ck-attention` (it silently corrupts TRELLIS.2 meshes), `--use-sage-attention`, bare `--fast`,
or `--fp16-vae`/`--bf16-vae`. Remove the variable when you are done.

## Uninstalling and cleaning up

*Settings > Apps > Local3D* removes the program and offers to delete the runtime and settings. Model files and your
`Documents\Local3D` folder are kept; delete those folders yourself to reclaim the space.
