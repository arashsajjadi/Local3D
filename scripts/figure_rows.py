#!/usr/bin/env python3
"""Compose a captioned comparison figure for the documentation: one row per subject, one column per image.

    python scripts/figure_rows.py out.jpg --captions "Picture,Before,After" \
        --row picture_a.jpg before_a.png after_a.png --row picture_b.jpg before_b.png after_b.png [--cell 360] [--quality 88]

Every image is scaled to fit a square cell on a dark background; the captions are printed once above the columns.
"""
import argparse

from PIL import Image, ImageDraw


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("--captions", required=True, help="comma-separated column captions")
    ap.add_argument("--row", nargs="+", action="append", required=True, metavar="IMAGE")
    ap.add_argument("--cell", type=int, default=360)
    ap.add_argument("--quality", type=int, default=88)
    a = ap.parse_args()
    captions = [c.strip() for c in a.captions.split(",")]
    cols = max(len(r) for r in a.row)
    if len(captions) != cols:
        ap.error(f"{len(captions)} captions for {cols} columns")
    head = 30
    sheet = Image.new("RGB", (cols * a.cell, head + len(a.row) * a.cell), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for c, text in enumerate(captions):
        d.text((c * a.cell + 10, 9), text, fill=(225, 225, 225))
    for r, row in enumerate(a.row):
        for c, path in enumerate(row):
            im = Image.open(path).convert("RGB")
            im.thumbnail((a.cell - 8, a.cell - 8))
            sheet.paste(im, (c * a.cell + (a.cell - im.width) // 2, head + r * a.cell + (a.cell - im.height) // 2))
    sheet.save(a.out, quality=a.quality, optimize=True)
    print("wrote", a.out, sheet.size)


if __name__ == "__main__":
    main()
