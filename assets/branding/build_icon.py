"""Regenerate icon.ico / icon-256.png from the geometry in icon.svg (requires Pillow).

    python assets/branding/build_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SS = 4  # supersampling factor
BASE = 256 * SS

TOP = [(128, 22), (218, 74), (128, 126), (38, 74)]
LEFT = [(38, 74), (128, 126), (128, 234), (38, 182)]
RIGHT = [(128, 126), (218, 74), (218, 182), (128, 234)]


def scaled(points):
    return [(x * SS, y * SS) for x, y in points]


def render() -> Image.Image:
    img = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon(scaled(TOP), fill="#5EEAD4")
    d.polygon(scaled(LEFT), fill="#14B8A6")
    d.polygon(scaled(RIGHT), fill="#0F766E")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.line([(38 * SS, 74 * SS), (218 * SS, 74 * SS)], fill=(255, 255, 255, 90), width=4 * SS)
    return Image.alpha_composite(img, overlay).resize((256, 256), Image.LANCZOS)


def main() -> None:
    icon = render()
    icon.save(HERE / "icon-256.png")
    icon.save(
        HERE / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("wrote icon-256.png and icon.ico")


if __name__ == "__main__":
    main()
