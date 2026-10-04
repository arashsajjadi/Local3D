#!/usr/bin/env python3
"""Print GitHub release notes for a version: its CHANGELOG section plus the standard install footer.

    python scripts/release_notes.py 0.1.0 > release-notes.md
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FOOTER = """
---

### Install

1. Download **Local3D-Setup-{v}.exe** below (verify it with `SHA256SUMS.txt`; build provenance is attested on this release).
2. Run it. Windows SmartScreen will warn because the installer is **not code-signed**: *More info* > *Run anyway*.
3. Start **Local3D** from the Start menu. On first start it asks before downloading the ComfyUI runtime (about 2 GB)
   and the model files (15 GB, plus 7 to 16 GB for Prompt to 3D). After that it works offline.

### Requirements

Windows 10/11 x64, an NVIDIA RTX 20-series or newer GPU (12 GB+ recommended; tested on an RTX 5080 16 GB), about 30 GB of
disk space, internet for the first start. See [docs/INSTALL.md](https://github.com/arashsajjadi/Local3D/blob/v{v}/docs/INSTALL.md).

### Models

Pixal3D and TRELLIS.2 (image to 3D), FLUX.2 klein 4B (reference pictures). Licenses differ from Local3D's MIT license:
[THIRD_PARTY_NOTICES.md](https://github.com/arashsajjadi/Local3D/blob/v{v}/THIRD_PARTY_NOTICES.md).

### Known limitations

See [docs/TROUBLESHOOTING.md](https://github.com/arashsajjadi/Local3D/blob/v{v}/docs/TROUBLESHOOTING.md) and the
[quality notes](https://github.com/arashsajjadi/Local3D/blob/v{v}/docs/QUALITY.md). Single-picture 3D invents the sides it cannot see.
"""


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    v = sys.argv[1].lstrip("v")
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## \[{re.escape(v)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: )", text, re.S | re.M)
    if not m:
        print(f"CHANGELOG.md has no section for {v}", file=sys.stderr)
        return 1
    print(m.group(1).strip() + "\n" + FOOTER.format(v=v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
