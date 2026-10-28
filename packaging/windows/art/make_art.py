"""Draws the Windows installer's artwork from the app's mark and fonts, so Setup looks like the
review screen and getmabillon.com: warm paper, the ink ledger mark, the serif wordmark.

    python packaging/windows/art/make_art.py

Writes wizard.bmp and wizard-small.bmp at 100, 150 and 200 percent scaling (Inno Setup picks
the size closest to the screen's) and mabillon.ico. Needs Pillow; run it again after changing
the mark in ui/theme.py and commit the files.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE.parents[2] / "ui" / "static" / "fonts"
PAPER = (247, 245, 240)
INK = (20, 20, 20)
MUTED = (95, 90, 81)
LINE = (228, 224, 216)


def mark(size: int, bg: tuple[int, int, int] = PAPER) -> Image.Image:
    """The ledger mark (ui/theme.py MARK) drawn at size x size, on bg."""
    s = size / 24
    im = Image.new("RGBA", (size, size), bg + (255,) if bg else (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((2.75 * s, 2.75 * s, 21.25 * s, 21.25 * s), radius=5 * s, fill=INK)
    w = max(1, round(1.5 * s))

    def stroke(x1: float, y1: float, x2: float, y2: float, alpha: float) -> None:
        c = tuple(round(INK[i] + (PAPER[i] - INK[i]) * alpha) for i in range(3))
        d.line((x1 * s, y1 * s, x2 * s, y2 * s), fill=c, width=w)

    stroke(12, 6.5, 12, 17.5, 1)
    for y in (9, 12, 15):
        stroke(6.75, y, 9.25, y, 0.9)
    stroke(14.75, 9, 17.25, 9, 0.55)
    stroke(14.75, 12, 16, 12, 0.55)
    return im


def wizard(scale: float) -> Image.Image:
    """The tall image on the welcome and finish pages."""
    w, h = round(164 * scale), round(314 * scale)
    im = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    m = mark(round(44 * scale))
    im.paste(m, (round(22 * scale), round(30 * scale)), m)
    serif = ImageFont.truetype(str(FONTS / "instrument-serif-latin-400-normal.woff2"), 30 * scale)
    sans = ImageFont.truetype(str(FONTS / "ibm-plex-sans-latin-wght-normal.woff2"), 10.5 * scale)
    d.text((22 * scale, 92 * scale), "Mabillon", font=serif, fill=INK)
    d.line((22 * scale, 140 * scale, w - 22 * scale, 140 * scale), fill=LINE, width=1)
    for i, line in enumerate(("Audits government", "claims about phone", "evidence.")):
        d.text((22 * scale, (152 + i * 15) * scale), line, font=sans, fill=MUTED)
    d.line((w - 1, 0, w - 1, h), fill=LINE, width=1)
    return im


def small(scale: float) -> Image.Image:
    """The square in the top corner of the inner pages."""
    n = round(55 * scale)
    return mark(n).convert("RGB")


def main() -> None:
    for scale, tag in ((1, "100"), (1.5, "150"), (2, "200")):
        wizard(scale).save(HERE / f"wizard-{tag}.bmp")
        small(scale).save(HERE / f"wizard-small-{tag}.bmp")
    icon = mark(256, bg=None)
    icon.save(HERE / "mabillon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)])


if __name__ == "__main__":
    main()
