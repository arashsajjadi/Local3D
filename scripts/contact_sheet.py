#!/usr/bin/env python3
"""Tile images into one labelled contact sheet (dev tool for reviewing renders).

    python scripts/contact_sheet.py out.png a.png b.png c.png ... [--cols 3] [--cell 520] [--crop x0,y0,x1,y1]

--crop takes fractions of each image (0-1), e.g. 0.1,0.05,0.6,0.5 to zoom on a region such as the raised hand.
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--cell", type=int, default=520)
    ap.add_argument("--crop")
    a = ap.parse_args()
    box = [float(v) for v in a.crop.split(",")] if a.crop else None
    cells = []
    for p in a.images:
        im = Image.open(p).convert("RGB")
        if box:
            w, h = im.size
            im = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
        im.thumbnail((a.cell, a.cell))
        cells.append((Path(p).stem, im))
    rows = (len(cells) + a.cols - 1) // a.cols
    sheet = Image.new("RGB", (a.cols * a.cell, rows * (a.cell + 22)), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(cells):
        x, y = (i % a.cols) * a.cell, (i // a.cols) * (a.cell + 22)
        d.text((x + 6, y + 4), name, fill=(220, 220, 220))
        sheet.paste(im, (x + (a.cell - im.width) // 2, y + 22))
    sheet.save(a.out)
    print("wrote", a.out, sheet.size)


if __name__ == "__main__":
    main()
