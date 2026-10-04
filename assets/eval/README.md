# Subject-routing evaluation pictures

Eleven pictures, one per kind of subject that Auto has to tell apart, used by `scripts/check_routing.py` and described in
[docs/CHARACTER_ROUTING_DECISION.md](../../docs/CHARACTER_ROUTING_DECISION.md). They are **not installed** by the installer.

| Picture | Kind | What Auto should do |
| --- | --- | --- |
| `portrait_woman`, `glasses_man`, `raised_hand_woman` | head-and-shoulders photographs, one with glasses, one with a raised hand | Character bust |
| `comic_general`, `armored_knight` | half-length characters (a comic general saluting, a knight raising a fist) that fill the frame and are cut off by it: the situation of the regression picture | Character bust, cut below the chest |
| `comic_wizard` | comic illustration, face hidden by a beard and hat | Object, with a "not sure: a person, but no large clear face" note (choosing *Character bust* fixes it) |
| `full_body_walker` | full-length photograph (the face is small) | Object, with the same note |
| `figurine_fox`, `bicycle_wheel`, `fern_plant` | ceramic figurine, thin spokes, thin leaves | Object |
| `toy_astronaut` | vinyl toy with a human-like face | Object, with a "a face but no person: toy, doll or statue" note |

`expected.json` holds these answers; `prompts.json` holds the text that made each picture.

## Provenance and licence

Generated for this project with FLUX.2 klein 4B (Apache-2.0 weights) through Local3D's own *Prompt to 3D* reference step
(`scripts/make_eval_set.py`, seed 20261004, or 222 for the two half-length characters; 1024 x 1024). Nothing was copied from a photograph or an artwork, and the
people shown are synthetic: they do not depict real individuals. The pictures are released under the repository's MIT licence.
