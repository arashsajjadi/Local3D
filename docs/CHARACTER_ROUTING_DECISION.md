# Subject routing and the Character bust workflow: decision record

**Status:** decided for v0.2.0. Evidence: [CHARACTER_FAILURE_ANALYSIS.md](CHARACTER_FAILURE_ANALYSIS.md), the measurements below,
and the primary sources linked in the candidate table. Everything measured here was run on one machine (RTX 5080, 16 GB,
Windows 11, ComfyUI 0.38.0); the numbers show what happened there, not a promise.

## The question

Before asking *which model should run*, ask *what kind of reconstruction problem is this picture?* A mug, a toy, a thin
bicycle wheel and a person saluting are four different problems. In v0.1.x they all went through the same steps, and a
saluting officer came out with a flat paddle for a hand. The failure was mostly **framing** (the figure filled the picture, so
the face and hand reached the model at low resolution) and, for one model, a **family mismatch**, not a missing model.

## Decision in brief

1. Keep **Pixal3D** as the one default for objects *and* characters. No candidate we could run beat it on this picture.
2. Add **input-aware routing** to *Image to 3D*, from two small detectors that ship with ComfyUI's core nodes: RT-DETR (person)
   and MediaPipe (face). They run first, on the original picture, and Local3D prints what they found and what it decided.
3. Add a real **Character bust** workflow: detect, cut the picture below the chest, remove the background and frame the
   *bust* (not the whole picture), run Pixal3D, say plainly that the hidden surfaces are inferred.
4. A **Subject** control (Auto, Object, Character bust, Complex) lets the user overrule Auto. Auto never silently picks a
   high-impact route from weak evidence: when the signals disagree it keeps the plain Object workflow and says so.
5. Real extra views beat invented ones: an optional **Character from views** app feeds two or four *real* views to
   Pixal3D's multi-view mode (one optional 5.6 GB download).
6. **Not added:** generated auxiliary views (measured worse), Hunyuan3D-2mv, HumanNOVA, PSHuman, DiGS-Avatar,
   Unique3D / Wonder3D / Era3D, SAM 3D Body. Reasons below.

## Routing matrix

| Problem | Typical picture | What Auto looks at | Workflow | Override |
| --- | --- | --- | --- | --- |
| **Rigid object, product, prop** | mug, chair, tool, car | no face, no person | **Object**: Pixal3D, whole picture | Subject = Object |
| **Toy, doll, figurine, statue** | vinyl toy, ceramic fox, bust of marble | a face but **no person** (the person detector does not fire), or neither | **Object**: whole figure, so legs and base are kept. A note says "a face but no person: this may be a toy, doll or statue" | Subject = Character bust crops to the upper body |
| **Human or stylised character, head and shoulders or half length** | portrait, comic, game art | a face (>= 0.5) that is >= 9 % of the picture height, **and** a person (>= 0.6) or a face filling >= 35 % of the height | **Character bust**: bust cut (below) then Pixal3D | Subject = Object keeps the whole picture |
| **Person without a large, clear face** | full-length figure, helmet or hood, beard and hat, a comic with a hidden face | a person (>= 0.6) but the face score is < 0.5 or the face is under 9 % of the picture height | **Object**, whole picture, with the note "not sure: a person, but no large clear face". Expect softer hands and face on a full-length figure | Subject = Character bust crops to the upper body |
| **Thin or open shapes** | bicycle wheel, fern, wire, cloth | cannot be detected reliably by a light detector | Never automatic. The user picks **Complex**: TRELLIS.2 (it handles open, thin geometry; it turned a full-bleed character into a plane, which is why it is never chosen silently for people) | Subject = Complex, or Model = TRELLIS.2 |
| **Real views available** | turnaround sheet, photos from several sides | the user supplies them | **Character from views** app: Pixal3D multi-view, real views, nothing invented | n/a |

Rules that hold in every row: nothing is downloaded or generated without a visible step; a *generated* picture is never
treated as a measurement; the user's explicit **Model** choice beats the subject's suggestion (a character is never
sent to TRELLIS.2 unless the user asks).

## Signals and thresholds

All local, all Comfy Core nodes, all in `data/presets.json` ("routing"):

| Signal | Source | Threshold | Why |
| --- | --- | --- | --- |
| person score | RT-DETR v4 (COCO "person"), best detection | >= 0.6 | detector scores are 0 to 1; 0.6 keeps clear people and drops guesses |
| face score | MediaPipe face landmarker, best detection | >= 0.5 | a conventional "probably a face" level |
| close portrait | face height / picture height | >= 0.35 | a head that large may fill the frame so completely that the person detector fails |
| bust-sized face | face height / picture height | >= 0.09 | below that the figure is full length; cutting it to a bust would remove the legs, so Auto keeps it as Object |
| bust cut line | face top + **2.7** face heights | skipped when it would remove less than 5 % of the picture | measured in the failure analysis (2.2 too tight, 3.2 less facial detail). Choosing Character bust yourself cuts whenever a face is found |

What the detectors reported for the pictures used to set and check these rules (face score / person score):

| Picture | Face | Person | Auto's answer |
| --- | --- | --- | --- |
| the officer comic (private) | 0.73 | 0.93 | Character bust, cut at row 1059 of 1679 |
| `portrait_woman` | 0.91 | 0.96 | Character bust, whole picture |
| `glasses_man` | 0.89 | 0.96 | Character bust, whole picture |
| `raised_hand_woman` | 0.96 | 0.96 | Character bust, whole picture |
| `comic_wizard` (face hidden by beard and hat) | 0.42 | 0.94 | Object + "not sure" note |
| `full_body_walker` (small face) | 0.48 | 0.94 | Object + "not sure" note |
| `toy_astronaut` | 0.90 | 0.00 | Object + toy note |
| `figurine_fox`, `bicycle_wheel`, `fern_plant` | 0.00 | 0.00 | Object |

Honest limits of this calibration: ten pictures, not a benchmark. The face and person minimums were fixed before the
evaluation set existed; the "a face needs a person (or a very large face)" rule was added after the first run sent a vinyl toy
to the bust workflow and cut its legs off (face 0.90, person 0.00). `comic_wizard` shows the cost of caution: Auto does not
guess, it says "not sure" and one click on *Character bust* fixes it. The pictures are in `assets/eval/` and
`python scripts/check_routing.py <runtime> <models>` re-checks every answer in seconds (no 3D generation).

## What the Character bust workflow does

1. **Looks at the original picture** (before any cut-out): person and face detectors, about 2 seconds.
2. **Cuts the picture below the chest** (rows 0 to face top + 2.7 face heights) when the face is large enough. The cut is made
   on the picture *and* on the user's own transparency, if they supplied one, so both stay aligned.
3. **Removes the background of the bust** (BiRefNet) and **frames the bust** (crop-to-mask, padding) instead of the whole picture.
   Order matters: the old order framed the whole picture first, which is why the face arrived at about 136 px.
4. **Pixal3D** builds the shape and textures with the user's Quality, Output and Seed, exactly as for objects.
5. **Writes a report** next to the model, in plain words: what was detected (with scores), which subject was chosen and by
   whom ("Auto picked it" / "your choice"), the framing (full picture, or the cut rows), a reminder that the back and far
   side are inferred, and, when relevant, the "not sure" or "toy, doll or statue" note.

Example report for the officer picture:

```
Subject: Character bust (Auto picked it)
Looked for: a face (score 0.73) and a person (score 0.93); scores run from 0 to 1.
Framing: cut below the chest, rows 0 to 1059 of 1679 kept, so the face and hands get more detail.
Hidden surfaces (the back and the far side) are inferred, not measured.
```

It is a **static textured bust**, not a rigged avatar: there is no skeleton, no blendshapes and no SMPL body.

## Candidates evaluated

Primary sources were read for each; nothing was integrated "because it is newer". Sizes are what the sources state or we measured.

| Candidate | What it is | Fit for Local3D (16 GB, Windows, GLB, core nodes) | Licence | Verdict |
| --- | --- | --- | --- | --- |
| [Pixal3D](https://github.com/TencentARC/Pixal3D) | pixel-aligned image to 3D; single and multi-view; official ComfyUI core nodes | yes; 5.6 GB DiT; measured 14 GB peak GPU use in total | MIT | **Default**, objects and characters |
| [TRELLIS.2](https://github.com/microsoft/TRELLIS.2) | object-centric image to 3D with PBR | yes through core nodes (12.6 GB peak measured; its README lists 24 GB for the reference code); returned a plane for a full-bleed character | MIT (the reference code's rendering libraries have separate terms; core nodes do not use them) | **Complex** shapes, by choice |
| [Hunyuan3D-2mv](https://github.com/Tencent-Hunyuan/Hunyuan3D-2) | multi-view (front, left, back) shape model, 1.1 B; README: 6 GB for shape, 16 GB with texture | core nodes can run the shape model, but texturing needs Tencent's own code outside core nodes | **Tencent Hunyuan 3D 2.0 Community License**: not valid in the EU, UK and South Korea; outputs may not be used to improve other AI models; a 1 million monthly-user cap; notices and an acceptable-use policy travel with redistribution | **Not added.** A restrictive, territory-limited licence does not belong in a default download, and its multi-view input adds nothing Pixal3D's multi-view mode does not already do under MIT. It could become an optional pack for users outside those territories. |
| [HumanNOVA](https://github.com/HumanNOVA/HumanNOVA) (CVPR 2026) | large reconstruction model with an SMPL body prior; triplane to mesh | conda environment on CUDA 12.1, HMR2 pose estimate, SMPL assets from a registration-gated download; photoreal humans (stylised input not documented); the paper reports trouble with occlusion and plausible back textures | the repository has **no licence file**; SMPL is non-commercial | **Not added**: unclear licence, not core-node, no evidence for stylised input |
| [PSHuman](https://github.com/pengHTYX/PSHuman) | cross-scale multi-view diffusion with explicit remeshing | its README states the current model needs **over 40 GB** of VRAM | MIT | **Unsuitable** for a 16 GB default |
| DiGS-Avatar ([paper](https://arxiv.org/abs/2608.20759)) | UV-space diffusion on SMPL-X, animatable 3D Gaussian avatar | output is a Gaussian avatar, not a GLB mesh | not checked further | **Rejected**: it would turn Local3D into an avatar/Gaussian platform |
| [Unique3D](https://github.com/AiuniAI/Unique3D), [Wonder3D](https://github.com/xxlong0/Wonder3D), [Era3D](https://github.com/pengHTYX/Era3D) | multi-view diffusion plus reconstruction | want frontal, rest-pose input; occlusion hurts ("four / six views cannot cover the complete object"); Wonder3D works at 256 px | MIT, MIT, **AGPL-3.0** | **Not added**: pose-sensitive, low resolution, not in core nodes |
| [SAM 3D Body](https://github.com/facebookresearch/sam-3d-body) | parametric body mesh (Momentum Human Rig) with hand and pose accuracy | a naked body prior, not a clothed textured result | "SAM License" | **Not added**; a body prior was not needed once framing was fixed |
| Qwen-Image-Edit-2511 + Lightning 4-step + [Multiple-Angles LoRA](https://huggingface.co/fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA) | local image-edit model that re-draws a picture from another camera angle | fits 16 GB (int8 build; 14 to 22 s per view, 15.3 GB peak measured) | Apache-2.0 (all three) | **Evaluated, measured worse, not shipped** (below) |
| Qwen-Image-2.1 | newer unified generator/editor | n/a | `qwen-research` (non-commercial) | **Not usable** as a default |
| RT-DETR v4, MediaPipe face landmarker | the two detectors, as ComfyUI core nodes | 1 to 2 s, small | Apache-2.0 (RT-DETR via Comfy-Org's MIT repack), Apache-2.0 | **Adopted** |

### Why generated views were not shipped

The auxiliary-view stage asked Qwen-Image-Edit-2511 (with the angle LoRA) for left, back and right views of the bust, then
fed them to Pixal3D's multi-view mode. Findings, on the officer picture:

* Scale and framing drifted from view to view ("medium shot" even produced full-length figures; "close-up" was needed).
* Details were **re-drawn, not preserved** (ribbons, hand, glasses differ in every view), so the model received contradictory evidence.
* The 3D result was **worse than the single bust crop**, and cost three more model loads on a 16 GB card.

A generated view is a guess presented as evidence. Single-view fidelity beat it, so it stays out. If it is ever added it must
show the views first and let the user reject them, and never be mixed with real views silently.

Real views are different: with the official four-view sample sheet the back and the far side became real and the result was
very good. That is the **Character from views** app (optional Pixal3D multi-view model, 5.6 GB, MIT).

## Hardware, measured

NVIDIA RTX 5080 (16 GB), Windows 11, 64 GB RAM, ComfyUI 0.38.0 with Local3D's usual launch flags (no `--lowvram`, no allocator
tweaks: ComfyUI's dynamic VRAM brings each stage's weights in when they are needed and gives them up under memory pressure, so the
stages run one after another and nothing had to be configured). One picture, *Balanced*, *High fidelity*, three seeds. Other programs held
about 3 GB of the card during these runs; "GPU memory in use" is the whole card, as `nvidia-smi` reports it.

| Run (officer picture) | Time | GPU memory in use, peak | Engine RAM, peak |
| --- | --- | --- | --- |
| Subject detection alone (what *Auto* adds to every run) | 2 s once the detectors are loaded (8 to 20 s the first time) | small (124 MB + 5 MB of weights) | n/m |
| **Object**, whole picture (the v0.1.x behaviour) | 131 s, 147 s, 161 s | 14.2, 14.6, 14.6 GB | 8.4 to 8.5 GB |
| **Character bust** (Auto) | 227 s warm; 211 s and 257 s as the first run after starting | 14.4, 14.5, 14.0 GB | 8.5 to 8.6 GB |
| TRELLIS.2, whole picture (the plane) | 78 s | 12.6 GB | n/m |

Reading it: the bust workflow needs **the same memory** as the object workflow (about 11.5 GB above the 3 GB other programs held, with
dynamic VRAM using whatever is free) and about **1.5 times the time** on this picture. The extra time is the point: the bust fills more of the model's
input frame than the whole picture does, so there are more occupied voxels to refine, mesh and bake. For pictures that stay on the Object
workflow the only added cost is the two seconds of detection. For the generated-view experiment that was not shipped: one view from the image-editing model took
14 to 22 s at 15.3 GB (the card was full), and Pixal3D's multi-view stage 190 to 271 s at 13.6 to 15.3 GB.

## Quality comparison

The officer picture, scored against the rubric the task set: hand and salute 25 %, face and identity 20 %, glasses 10 %, headwear 10 %,
shoulders and epaulettes 15 %, torso and uniform 10 %, rear and overall coherence 10 %. Each criterion is 0 to 10 (0 absent or degenerate;
3 crude, a hand without separate fingers; 5 soft; 7 good with minor defects; 10 faithful and clean), judged from renders: front,
three-quarter, back, and a front *clay* render that shows the real geometry. Seven models: the whole-picture route (v0.1.x) and the new
Auto route at seeds 1234, 2 and 3, and TRELLIS.2 on the whole picture. **These are judgements by eye, not measurements.** Two were made:

* a **blind review** by a second, independent model instance that saw only anonymised, shuffled sheets and the reference picture;
* the author's own scoring (not blind).

| Criterion (weight) | Whole picture, blind mean of 3 seeds | **Character bust**, blind mean of 3 seeds |
| --- | --- | --- |
| Hand and salute (25) | 3.5 | **5.3** |
| Face and identity (20) | 5.0 | **6.5** |
| Glasses (10) | 4.7 | **6.2** |
| Headwear (10) | 6.5 | **7.3** |
| Shoulders and epaulettes (15) | 6.5 | **7.0** |
| Torso and uniform (10) | 5.8 | **6.7** |
| Rear and overall coherence (10) | **7.2** | 5.8 |
| **Total of 100** | **52.7** (seeds: 52, 56, 50) | **62.8** (seeds: 66.5, 63.5, 58.5) |

TRELLIS.2 on the whole picture scored **0** (a flat textured plane). The author's own, more generous scoring: whole picture **48.5**, Character bust **74.3**.

What to take from it:

* The two scorers agree on the direction and on the process each picture came from (the reviewer sorted the seven sheets into the three processes from
  the images alone). They differ in size: **+10 points blind, +26 points by the author**. Trust the smaller number.
* The gains are in what the cropping was meant to improve: hand, face, glasses, then headwear, shoulders and torso.
* **The hand is better, not solved.** On the clay render the whole-picture hand is a smooth paddle that ends at the ear; the bust hand reaches the visor as in the picture
  and shows a separate thumb and stepped fingertips, but the reviewer found no candidate with five cleanly separate fingers.
* **One criterion got worse: the back.** More detail brings more noise with it (stray scratches, a noisy cap top in one seed, small holes), while the whole-picture result is
  smoother (7.2 against 5.8). The lens colour and the back of the head still change with the seed, as they must: no picture shows them.

## 3D printing

An optional *3D print* output (a closed, watertight surface a slicer accepts, reported honestly with no printability guarantee) was
tried and **not shipped**. Measured on the officer bust (Pixal3D, Balanced, same seed), changing only the clean-up step ComfyUI's core nodes offer:

| Variant | Triangles | Components | Open edges | What it showed |
| --- | --- | --- | --- | --- |
| **Shipped:** unsigned-distance remesh (UDF) | 290 k | 465 (7.6 % of the triangles outside the largest) | 1 691 (0.19 % of all edges), in 112 small holes | not watertight, but there is **no large hole**: the base of the bust is closed |
| Signed-distance remesh (SDF, with QEF) | 158 k | 1 530 (83 % outside the largest) | 44 040 (9.3 %) | much worse: this mode needs a consistently oriented closed input surface, which the generated mesh is not |
| UDF, then *Fill Holes* (up to 1 024 boundary vertices) | 291 k | 445 | 1 619 | closed only 72 edges: the remaining holes are slits and thin gaps where braid leaves, glasses parts and ribbons meet, not clean loops |

So the core nodes cannot turn this output into a printable solid, and a "print mode" that only *sounds* printable would be dishonest
(the same conclusion as upstream issue #16147 about inner shells, already noted in [QUALITY.md](QUALITY.md)). What does hold: the bust ends in a closed, smoothly
rounded base (its colour there is arbitrary, because the picture shows nothing of it) and the high-resolution model is kept apart from
the optimised one: run once with *High fidelity* for the master, then again with *Game asset* (the generated shape is cached, so
the second run takes seconds); each run saves its own `.glb`. For printing, repair the mesh in Blender (3D-Print Toolbox) or in your slicer;
`python scripts/mesh_report.py model.glb` reports triangles, components, open edges and watertightness for any file.

## Licensing of what ships

| Item | Role | Licence | Where it lives |
| --- | --- | --- | --- |
| Pixal3D | shape and texture | MIT | core pack (already) |
| TRELLIS.2 | complex shapes | MIT | core pack (already) |
| RT-DETR v4 (Comfy-Org repack) | person detector | MIT repack of Apache-2.0 weights | **core pack, +124 MB** |
| MediaPipe face landmarker (Comfy-Org repack) | face detector | Apache-2.0 | **core pack, +5 MB** |
| Pixal3D multi-view DiT (int8) | Character from views | MIT | **optional pack, 5.6 GB**, asked for only when the app is opened |
| Evaluation pictures (`assets/eval`) | routing checks | MIT (generated with FLUX.2 klein 4B, Apache-2.0) | repository only, not installed |
| Example views (`assets/examples/Local3D_example_views_*`) | default pictures of the views app | MIT (renders of this project's own robot model) | installed with the app |

Labels used in the app and the docs: *permissive open source* (MIT, Apache-2.0), *open weights with a custom licence*
(DINOv3, already disclosed), *community licence* (Hunyuan3D, **not shipped**), *optional restricted model* (none ships).
Hunyuan3D's terms are summarised above rather than buried: if it is ever offered, it will be a separate opt-in pack with its
territory limits stated at the download prompt.

## The twelve decisions

1. **Rigid objects:** Pixal3D on the whole picture (*Object*). It stayed closest to the picture in the eight-object evaluation ([QUALITY.md](QUALITY.md)).
2. **Complex, thin or open shapes:** TRELLIS.2, **only by the user's choice** (*Complex*, or *Model: TRELLIS.2*). Upstream positions it for open and thin
   geometry; in our own evaluation both models kept spindles and open tops, so its edge is modest, and it returned a plane for a full-bleed character.
   Nothing detects "thin" reliably with a light detector, so Auto never sends a picture there.
3. **Toys and figurines:** *Object*, whole figure, so legs and base survive. A face detected without a person adds the note "a face but no person: this may be a toy,
   doll or statue".
4. **Real human busts:** *Character bust*: cut below the chest, remove the background, frame the bust, Pixal3D.
5. **Stylised human and character busts:** the same workflow. It was measured on a comic officer (private picture) and checked on synthetic comic and armoured characters.
6. **Single-image fallback:** the best crop of the one picture goes to Pixal3D; the back and the far side are labelled as inferred in the report, and the seed
   decides the rest. Nothing is invented from other models.
7. **Two to four real views:** the *Character from views* app (Pixal3D multi-view): front, left, back, right, or just front and back.
8. **Hunyuan3D-2mv:** **not added.** Its licence excludes the EU, UK and South Korea, forbids using outputs to train other AI models and caps users; core nodes run only its
   shape stage; Pixal3D's multi-view mode already does the same job under MIT. It could return as an opt-in pack, with those terms shown at the download prompt.
9. **HumanNOVA:** **not added.** No licence file in the repository, SMPL assets that are non-commercial and registration-gated, a conda/CUDA 12.1 stack outside core
   nodes, trained on photoreal humans with no documented stylised-input behaviour, and the authors' own limits (occlusion, back textures).
10. **Auxiliary-view generator:** **not added.** Measured worse than the single bust crop because each generated view re-draws the details. If one is ever offered, the
    views must be shown first, be rejectable, and never be mixed with real views silently.
11. **Why the others were rejected:** PSHuman needs over 40 GB; DiGS-Avatar outputs Gaussian avatars, not GLB; Unique3D, Wonder3D and Era3D want frontal rest-pose input, work at low
    resolution and (Era3D) are AGPL-3.0; SAM 3D Body gives an unclothed body prior; Qwen-Image 2.1 is non-commercial. The table above has the sources.
12. **Peak VRAM and timings on this RTX 5080 (16 GB):** 14 to 14.6 GB of the card in use at peak with about 3 GB held by other programs, 8.5 GB of engine RAM,
    Object 131 to 161 s, Character bust 227 s warm, detection 2 s, TRELLIS.2 78 s. Details in *Hardware, measured*.

## What would change this

* A permissively licensed human-specific model that runs in 16 GB, accepts stylised input and outputs a clothed GLB would
  justify a separate route (none exists today that meets all four).
* A view generator that preserves details (not just identity) across angles would justify showing generated views to the
  user for approval.
* A better "is this a toy or a person" signal than two COCO-trained detectors. Today the answer is a note and a one-click override.
