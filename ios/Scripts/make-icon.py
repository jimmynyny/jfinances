#!/usr/bin/env python3
"""The app icon: a PixelSparkline on the dark panel (docs/70 "Pixel layer").

Drawn, not designed in a tool, so it is reproducible. A grid of unlit cells,
a rising trace lit in ink with dimmer cells beneath it, the newest cell in the
accent, and registration marks at the corners. One opaque 1024 px master; iOS
makes the other sizes and applies the mask.
"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
PANEL = (22, 23, 25)       # --mu-panel (dark)
OFF = (37, 39, 43)         # --mu-pixel-off
INK = (247, 247, 243)      # --mu-ink
ACCENT = (255, 106, 52)    # --mu-accent
REG = (74, 77, 83)         # --mu-reg

COLS, ROWS = 9, 9
# The trace's lit row per column (0 = bottom): a climb with a dip, like a year.
TRACE = [1, 2, 2, 4, 3, 5, 6, 6, 8]


def mix(c, bg, a):
    return tuple(round(x * a + y * (1 - a)) for x, y in zip(c, bg))


def main(out=Path(__file__).resolve().parents[1] / "App/Assets.xcassets/AppIcon.appiconset/icon-1024.png"):
    img = Image.new("RGB", (S, S), PANEL)
    d = ImageDraw.Draw(img)
    grid = int(S * 0.62)
    pitch = grid / COLS
    gap = pitch * 0.18
    cell = pitch - gap
    x0 = (S - grid + gap) / 2
    y0 = (S - grid + gap) / 2
    for c in range(COLS):
        lit = TRACE[c]
        for r in range(ROWS):
            if r == lit:
                color = ACCENT if c == COLS - 1 else INK
            elif r < lit:
                color = mix(INK, PANEL, 0.38 if lit - r <= 2 else 0.16)
            else:
                color = OFF
            x = x0 + c * pitch
            y = y0 + (ROWS - 1 - r) * pitch
            d.rectangle((round(x), round(y), round(x + cell), round(y + cell)), fill=color)
    # Registration marks: an L at each corner, outside the grid.
    m = int(S * 0.115)
    arm = int(S * 0.07)
    w = max(6, int(S * 0.012))
    for cx, cy, sx, sy in ((m, m, 1, 1), (S - m, m, -1, 1), (m, S - m, 1, -1), (S - m, S - m, -1, -1)):
        d.rectangle(sorted_box(cx, cy, cx + sx * arm, cy + sy * w), fill=REG)
        d.rectangle(sorted_box(cx, cy, cx + sx * w, cy + sy * arm), fill=REG)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(out)


def sorted_box(x1, y1, x2, y2):
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


if __name__ == "__main__":
    main()
