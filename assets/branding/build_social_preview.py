#!/usr/bin/env python3
"""Build the 1280x640 GitHub social preview from the real evaluation renders in docs/images/examples-2.jpg.

    python assets/branding/build_social_preview.py        ->  assets/branding/social-preview.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
BG, FG, MUTED, ACCENT = (24, 24, 28), (244, 246, 247), (160, 168, 172), (30, 190, 172)
FONTS = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in (FONTS / name, Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def crop(sheet: Image.Image, box, size):
    return sheet.crop(box).resize((size, size), Image.LANCZOS)


def main() -> None:
    sheet = Image.open(ROOT / "docs" / "images" / "examples-2.jpg").convert("RGB")
    canvas = Image.new("RGB", (1280, 640), BG)
    draw = ImageDraw.Draw(canvas)

    # right side: two "picture -> 3D model" rows, real renders (Pixal3D, Balanced)
    cell, gap, x0, y0 = 262, 18, 610, 56
    # inner squares of the evaluation sheet's cells (skips the 'reference' caption chip)
    rows = [((23, 1178, 323, 1478), (356, 1158, 692, 1494)),   # robot
            ((23, 56, 323, 356), (356, 36, 692, 372))]          # basket
    for r, (ref_box, out_box) in enumerate(rows):
        y = y0 + r * (cell + gap + 8)
        ref = crop(sheet, ref_box, cell)
        out = crop(sheet, out_box, cell)
        canvas.paste(ref, (x0, y))
        canvas.paste(out, (x0 + cell + 84, y))
        ax, ay = x0 + cell + 42, y + cell // 2
        draw.line((ax - 22, ay, ax + 16, ay), fill=ACCENT, width=6)
        draw.polygon([(ax + 28, ay), (ax + 10, ay - 14), (ax + 10, ay + 14)], fill=ACCENT)

    # left side: name, promise, three facts
    icon = Image.open(ROOT / "assets" / "branding" / "icon-256.png").convert("RGBA").resize((92, 92), Image.LANCZOS)
    canvas.paste(icon, (64, 70), icon)
    draw.text((170, 78), "Local3D", font=font("segoeuib.ttf", 76), fill=FG)
    draw.text((64, 214), "Turn a photo or a prompt", font=font("segoeuib.ttf", 40), fill=FG)
    draw.text((64, 264), "into a textured 3D model.", font=font("segoeuib.ttf", 40), fill=FG)
    small = font("segoeui.ttf", 29)
    for i, line in enumerate(("On your own NVIDIA GPU", "Offline, private, no account", "Exports a PBR .glb file")):
        y = 372 + i * 52
        draw.ellipse((66, y + 11, 82, y + 27), fill=ACCENT)
        draw.text((98, y), line, font=small, fill=MUTED)
    foot = font("segoeui.ttf", 22)
    draw.text((64, 548), "Windows  ·  MIT license", font=foot, fill=MUTED)
    draw.text((64, 580), "Pixal3D  ·  TRELLIS.2  ·  FLUX.2 klein", font=foot, fill=MUTED)

    out = ROOT / "assets" / "branding" / "social-preview.png"
    canvas.save(out, optimize=True)
    print("wrote", out, out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
