# Install and first start

## What you need

| | |
| --- | --- |
| **Windows** | 10 (version 2004) or 11, 64-bit. Microsoft Edge (already part of Windows) |
| **Graphics card** | NVIDIA RTX 20-series or newer with an up-to-date driver (580 or newer recommended). 12 GB of video memory or more is recommended; 16 GB is the comfortable target. Local3D is developed and tested on an RTX 5080 (16 GB). AMD, Intel and Apple GPUs are not supported yet |
| **Memory** | tested with 64 GB of RAM; lower amounts have not been measured |
| **Disk space** | about **8 GB** for the program and runtime, plus **15 GB** for the 3D models, plus **7 to 16 GB** if you add *Prompt to 3D* (depends on your GPU). Models can go on any drive |
| **Internet** | for the first start only (about 2 GB runtime + models). After that, generation works offline |

## Install

1. Download `Local3D-Setup-0.1.0.exe` from the [latest release](https://github.com/arashsajjadi/Local3D/releases/latest)
   (and, if you like, check it against `SHA256SUMS.txt` on the same page).
2. Run it. Windows may show **"Windows protected your PC"** because the installer is not code-signed yet:
   click **More info**, then **Run anyway**. No administrator rights are needed; it installs for your user only.
3. Leave *Start Local3D now* ticked and finish.

The installer is only about 2 MB. It does not download anything.

## First start (once)

1. **Runtime.** Local3D asks before downloading the ComfyUI runtime (about 2 GB, the official release from
   github.com/Comfy-Org/ComfyUI). It is checked against a checksum, unpacked, and takes about a minute on a fast connection.
2. **Models.** A window shows what is needed, how big it is, where it will be saved and how much space is free:
   * *Image to 3D* (15.2 GB) is required.
   * *Prompt to 3D* reference pictures (6.6 GB on RTX 50-series, 12.5 GB on RTX 40-series, 16.1 GB on older cards) is optional.
   Use **Change folder...** to put them on another drive. Downloads can be interrupted at any time and resume.
3. The **app window** opens. The very first start of the engine takes about half a minute longer than later ones.

You never see a console window, a Python install, a model folder or a node graph.

## Use it

* **Image to 3D** opens first. A sample picture is already selected; press **Run** to try it, or drop your own picture
  (one object, fully visible). Pick *Quality*: **Balanced** is recommended; *Fast* is a quick preview; *Maximum* needs
  the most GPU memory.
* **Prompt to 3D**: *Start > Local3D tools > Prompt to 3D*, or use the *Apps* button in the left bar of the window.
  Type what you want and press **Run**.
* **Reference pictures** makes up to four candidates in seconds. Pick the best, then choose it in *Image to 3D*.

Results are in **`Documents\Local3D\models\`** as `.glb` files. The 3D viewer shows the model; drag to rotate, scroll to
zoom, right-drag to pan. Each run also appears in the app's history.

## Start menu and pinning

The installer adds **Local3D** to the Start menu (type "Local3D" after pressing the Windows key). Windows does not allow
programs to pin themselves: to pin it, right-click the Start menu entry and choose **Pin to Start** (or **Pin to taskbar**).
Extra shortcuts (Prompt to 3D, Reference pictures, Download more models, Diagnostics) are in the **Local3D tools** folder.

## Where things are

| | |
| --- | --- |
| Program | `%LOCALAPPDATA%\Programs\Local3D` |
| Runtime, logs, settings, workspace | `%LOCALAPPDATA%\Local3D` |
| Model files | `%LOCALAPPDATA%\Local3D\models` or the folder you chose |
| Your results | `Documents\Local3D` |

To move the runtime or models, create `%LOCALAPPDATA%\Local3D\settings.json` before first start:
`{"dataDir": "D:\\Local3DData", "modelsDir": "D:\\Local3DModels"}`.
A model folder you already have from ComfyUI works too: matching files are verified and reused, never downloaded again.

## Update and uninstall

* **Update:** run the newer installer over the old one. Your runtime, models and results are kept.
* **Uninstall:** *Settings > Apps > Local3D*. It asks whether to also remove the runtime and logs. Model files and
  `Documents\Local3D` are never deleted for you.

## Already use ComfyUI?

The apps are a standard ComfyUI custom-node folder. With **ComfyUI 0.35 or newer** (0.38 tested), copy
`local3d_pack` into `ComfyUI\custom_nodes`, put the models from `data/models.json` in the usual model folders, restart, and
find the apps under *Templates > Extensions*. Open the *Apps* sidebar after saving them as workflows, or use the link
`/?template=Local3D_Image_to_3D.app&source=local3d_pack&mode=linear`. You still get the full graph: switch the app
to *Graph* with the toggle at the top.

## Unattended or scripted install

```
Local3D-Setup-0.1.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
"%LOCALAPPDATA%\Programs\Local3D\Local3D.exe" --yes
```
`--yes` accepts the default of every consent dialog (downloads the runtime and the models for your GPU).
