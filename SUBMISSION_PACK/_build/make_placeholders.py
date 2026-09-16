"""Draw the two grey "PHOTO GOES HERE" boxes that stand in for the photographs.

    python SUBMISSION_PACK/_build/make_placeholders.py

The figure numbers are read from ``add_photos.py``'s SLOTS table, so adding a
figure earlier in the write-up can never leave a box captioned "Figure 5" under
a caption that says Figure 6 again. Run it after changing SLOTS; it is not
needed to build or read the entry.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PHOTOS = HERE.parent / "photos"
SIZE = (1600, 900)
BACKDROP = (233, 236, 241)
PANEL = (247, 249, 251)
RULE = (176, 186, 199)
INK = (32, 54, 92)
MUTED = (110, 122, 140)

FONTS = ("/usr/share/fonts/truetype/liberation/LiberationSans-%s.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf")


def _font(size: int, bold: bool = False):
    for template in FONTS:
        for suffix in (("Bold", "-Bold") if bold else ("Regular", "")):
            try:
                return ImageFont.truetype(template % suffix, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _centre(draw, y: int, text: str, font, fill) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((SIZE[0] - (right - left)) / 2 - left, y - top), text,
              font=font, fill=fill)


def draw_placeholder(figure: int, filename: str, caption: str,
                     instruction: str) -> Path:
    image = Image.new("RGB", SIZE, BACKDROP)
    draw = ImageDraw.Draw(image)
    draw.rectangle((36, 36, SIZE[0] - 37, SIZE[1] - 37), fill=PANEL,
                   outline=RULE, width=3)
    _centre(draw, 330, f"FIGURE {figure} — PHOTO GOES HERE", _font(74, bold=True), INK)
    _centre(draw, 452, caption, _font(40), MUTED)
    _centre(draw, 524, instruction, _font(30), MUTED)
    out = PHOTOS / filename
    image.save(out, quality=92, optimize=True)
    return out


def main() -> int:
    from add_photos import SLOTS

    instructions = {
        "pi": "Replace this file: SUBMISSION_PACK/photos/%s",
        "team": "Replace this file: SUBMISSION_PACK/photos/%s",
    }
    captions = {
        "pi": "The Raspberry Pi 5 running Climate Mesh, dashboard on screen",
        "team": "Luis and Leo with the Pi running the flood scenario",
    }
    PHOTOS.mkdir(parents=True, exist_ok=True)
    for slot, (figure, filename, _default) in SLOTS.items():
        out = draw_placeholder(figure, filename, captions[slot],
                               instructions[slot] % filename)
        print(f"  wrote {out.relative_to(HERE.parent.parent)} (Figure {figure})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
