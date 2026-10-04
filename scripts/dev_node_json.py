#!/usr/bin/env python3
"""Print the UI-format JSON ComfyUI's own frontend creates for node types (dev tool for writing scripts/build_workflows.py).

    python scripts/dev_node_json.py RTDETR_detect MediaPipeFaceLandmarker ... > nodes.json

Hand-writing node JSON is error-prone (widget sockets, dynamic inputs, default widget values): ask the real frontend.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dev_comfy import Engine  # noqa: E402

_DATA = os.environ.get("LOCAL3D_DATA_DIR", os.path.join(os.environ.get("LOCALAPPDATA", ""), "Local3D"))
RUNTIME = os.environ.get("LOCAL3D_RUNTIME", os.path.join(_DATA, "runtime", "ComfyUI_windows_portable"))
MODELS = os.environ.get("LOCAL3D_MODELS_DIR", os.path.join(_DATA, "models"))


def main() -> int:
    types = sys.argv[1:]
    if not types:
        print(__doc__)
        return 2
    work = tempfile.mkdtemp(prefix="l3d_nodes_")
    with Engine(runtime=RUNTIME, models=MODELS, workdir=work, port=8341) as eng:
        c = eng._browser()
        js = ("(() => { const out = {}; for (const t of %s) { try { const n = LiteGraph.createNode(t); if (!n) { out[t] = null; continue; }"
              " app.graph.add(n); out[t] = n.serialize(); app.graph.remove(n); } catch (e) { out[t] = 'ERR ' + e; } } return JSON.stringify(out); })()") % json.dumps(types)
        print(c.js(js))
    return 0


if __name__ == "__main__":
    sys.exit(main())
