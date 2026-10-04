# Why a comic officer came out wrong: analysis of a character regression

Local3D v0.1.x treated every picture as the same kind of problem: remove the background, hand the picture to one model,
clean up the mesh. A user's picture of a uniformed officer saluting (a comic-style illustration) showed where that
breaks. This page records what was measured, what is unavoidable, and what was fixable. The decision that follows from it is in
[CHARACTER_ROUTING_DECISION.md](CHARACTER_ROUTING_DECISION.md).

The picture and every model made from it stay **outside the repository** (they are someone's artwork). This page
describes them and records numbers; it does not include them. The same procedure can be repeated with any picture
(see "Repeat it" at the end).

## The picture

| | |
| --- | --- |
| Size | 937 x 1679 px, flat purple background, comic ink lines |
| Subject | A man in a peaked cap with gold laurel braid, tinted rectangular glasses, epaulettes, a rack of ribbons and a chest badge, saluting with his right hand in three-quarter view |
| Framing | The figure fills **90 %** of the picture height (RT-DETR person box 932 x 1506 px) and is cut by the frame on three sides: the left sleeve, the right shoulder and the jacket at the bottom |
| Face | MediaPipe face box 220 x 245 px: **14.6 %** of the picture height |
| Background cut-out | BiRefNet's mask keeps the fingers, the glasses frames and the cap braid (checked on an overlay), so segmentation is not the problem |

## What the 3D result looked like

The user's own run (Pixal3D, *Balanced*, about 297 k triangles, 2048 px textures) and an identical re-run with a fixed seed:

* **Hand**: a flat paddle, the fingers fused into one slab, ending at the ear instead of at the visor. The clay render (no textures) shows it too, so the *geometry*
  is wrong, not the texture.
* **Face**: small and soft; the glasses read as one dark slab; the cap, laurel braid and epaulettes are present but shallow.
* **Proportions**: tall and narrow (0.54 m wide x 0.94 m tall against 0.86 x 0.89 m for the improved result below), with
  the arm pressed against the head and a long torso that is mostly belt and lower jacket.
* **Back**: a plausible, smooth jacket and head. It differs from run to run (seed) because nothing in the picture decides it.
* **TRELLIS.2 on the same picture**: a flat slab, 0.9955 x 0.9954 x **0.003** m, one component, watertight: a textured plane.

## Four possible causes, separated

| Cause | Verdict | Evidence |
| --- | --- | --- |
| **Single-view ambiguity** (the picture cannot say) | **Real, unavoidable** | The back of the head and cap, the back of the jacket, the far shoulder and ear, the underside of the visor and the shape of transparent lenses are not visible. They vary with the seed (bald, white-haired or tan head from behind; white, grey or black lenses). Only more real views fix these. |
| **Model-family mismatch** | **Real for TRELLIS.2, not for Pixal3D** | TRELLIS.2 is an object-centric model; given a full-bleed artwork it returned a textured plane. Pixal3D follows the picture (pixel-aligned features plus a camera estimate), so it is the right family for a reference-faithful result. No other candidate beat it for this input (see the decision record). |
| **Preprocessing and framing** | **The main fixable cause** | The cut-out touches the picture borders, so the crop-to-mask step (padding 1.1) keeps the *whole* picture: the face reaches the model at about 136 px of its 1024 px input, and the lower jacket and belt take over a third of the area. Cutting the picture below the chest first (rows 0 to 1059) raises the face to about 215 px (+58 %) and removes the least informative 37 %. |
| **Post-processing** (remesh, decimation, unwrap, bake) | **Ruled out** | The paddle hand is already in the raw clay geometry; triangle counts (297 k against 290 k) and texture sizes are the same in both runs. |

"The model hallucinated" is true only of the first row. The others are choices the pipeline made before the model ever ran.

## Experiments that led to the fix

All with Pixal3D, *Balanced*, same seed unless stated; renders from six angles, textured and clay.

| Experiment | Result |
| --- | --- |
| Whole picture (baseline) | Fused hand, small face, narrow figure (above). |
| Cut at 2.2 face heights below the face top | Hand and braid good, but the bust ends at the top of the chest pockets and the cap top gets a brown noise texture. Too tight. |
| **Cut at 2.7 face heights (just below the chest)** | The hand reaches the visor with a separate thumb and stepped fingertips (better, not five clean fingers), a clear face, glasses frames, wider natural shoulders, ribbons and braid in relief. **Chosen.** |
| Cut at 3.2 face heights (belt visible) | Still good; the face is smaller in the model's input again, so slightly less facial detail than 2.7. |
| Seeds 1234, 2 and 3 at 2.7 | Hand, cap, braid, epaulettes, ribbons and torso stay good in all three; the lenses, the back of the head and (once) the texture of the cap top change. |
| Auxiliary views made by a local image-editing model (Qwen-Image-Edit-2511 with a camera-angle LoRA), fed to Pixal3D's multi-view mode | Views drifted in scale and detail (hands and ribbons are re-drawn each time); the 3D result was **worse** than the single bust crop. Not shipped; see the decision record. |
| Real views (the official four-view sample sheet from the ComfyUI templates) | Very good: the back and the far side become real. This is what the optional "Character from views" app is for. |

## Measurements

NVIDIA RTX 5080 (16 GB), Windows 11, ComfyUI 0.38.0 (see the decision record for timings and memory).

| Result | Triangles | Components | Open edges | Bounding box W x H x D |
| --- | --- | --- | --- | --- |
| Whole picture, Pixal3D | 297 k | 78 (1.2 % floating) | 78 | 0.54 x 0.94 x 0.46 m |
| Bust cut, Pixal3D | 290 k | 426 (7.4 % floating) | 1 565 (0.18 %) | 0.86 x 0.89 x 0.51 m |
| Whole picture, TRELLIS.2 | 300 k | 1 | 0 | 1.00 x 1.00 x 0.003 m (a plane) |

The bust result has more small floating fragments (thin braid leaves, ribbons, glasses parts) because it carries more
fine detail; the largest component still holds 93 % of the triangles. Neither Pixal3D result is watertight (see "3D printing" in the
decision record).

## Repeat it

```
python scripts/mesh_report.py model.glb                       # triangles, components, open edges, watertightness
python scripts/render_glb_views.py model.glb out_dir --views front,q_right,back
python scripts/check_routing.py <runtime_dir> <models_dir>    # what Auto decides for the evaluation pictures
```
