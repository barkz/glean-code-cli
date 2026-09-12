#!/usr/bin/env python3
"""Draw the REPL's wordmark as a vector header image.

The CLI prints GLEAN_WORDMARK (glean_code/ui.py) in box-drawing characters.
Rendering that as SVG <text> would depend on whichever monospace font the
reader happens to have, and a missing glyph breaks the letterforms. So each
character cell is drawn instead: full blocks become rectangles, the box-
drawing pieces become strokes. The result is font-independent and crisp at
any size, and it stays in step with the CLI because it is generated from the
same string.

Regenerate after changing the wordmark:
    python3 .github/pages/make_banner.py

tests/test_pages_build.py fails if the committed SVG has drifted.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "glean-code-banner.svg"

CELL_W = 11
CELL_H = 20
STROKE = 2.4
PAD_X = 26
PAD_TOP = 26
META_GAP = 30
META_SIZE = 15
MARK = "#1cc8f0"
PLATE = "#1b1b23"
META_INK = "#8b8b9e"

# Matches render_getting_started()'s meta line with no token configured.
META = "Glean Code v0.1.0  ·  mode: mock  ·  no token (mock data)"


def wordmark_lines():
    from glean_code.ui import GLEAN_WORDMARK
    return [line for line in GLEAN_WORDMARK.split("\n") if line.strip()]


def cell_shapes(char, x, y):
    """SVG for one character cell at pixel origin (x, y)."""
    cx, cy = x + CELL_W / 2.0, y + CELL_H / 2.0
    right, bottom = x + CELL_W, y + CELL_H
    half = STROKE / 2.0

    if char == "█":  # full block
        return ['<rect x="%g" y="%g" width="%g" height="%g"/>' % (x, y, CELL_W, CELL_H)]
    if char == "═":  # horizontal
        return ['<rect x="%g" y="%g" width="%g" height="%g"/>' % (x, cy - half, CELL_W, STROKE)]
    if char == "║":  # vertical
        return ['<rect x="%g" y="%g" width="%g" height="%g"/>' % (cx - half, y, STROKE, CELL_H)]

    # corners: one arm horizontal to the near edge, one vertical
    corners = {
        "╔": (cx - half, right, cy - half, bottom),   # top-left
        "╗": (x, cx + half, cy - half, bottom),       # top-right
        "╚": (cx - half, right, y, cy + half),        # bottom-left
        "╝": (x, cx + half, y, cy + half),            # bottom-right
    }
    if char in corners:
        hx0, hx1, vy0, vy1 = corners[char]
        return [
            '<rect x="%g" y="%g" width="%g" height="%g"/>' % (hx0, cy - half, hx1 - hx0, STROKE),
            '<rect x="%g" y="%g" width="%g" height="%g"/>' % (cx - half, vy0, STROKE, vy1 - vy0),
        ]
    return []


def build_svg():
    lines = wordmark_lines()
    cols = max(len(line) for line in lines)
    art_w = cols * CELL_W
    art_h = len(lines) * CELL_H
    width = art_w + PAD_X * 2
    height = PAD_TOP + art_h + META_GAP + PAD_TOP

    shapes = []
    for row, line in enumerate(lines):
        for col, char in enumerate(line):
            if char == " ":
                continue
            shapes.extend(cell_shapes(char, PAD_X + col * CELL_W, PAD_TOP + row * CELL_H))

    meta_y = PAD_TOP + art_h + META_GAP
    return "\n".join([
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d"'
        ' role="img" aria-label="Glean Code">' % (width, height, width, height),
        '  <rect width="%d" height="%d" rx="12" fill="%s"/>' % (width, height, PLATE),
        '  <g fill="%s">' % MARK,
        "\n".join("    " + shape for shape in shapes),
        "  </g>",
        '  <text x="%d" y="%d" fill="%s" font-size="%d" font-family="ui-monospace,'
        ' SFMono-Regular, Menlo, Consolas, monospace" xml:space="preserve">%s</text>'
        % (PAD_X + CELL_W, meta_y, META_INK, META_SIZE, META),
        "</svg>",
        "",
    ])


def main():
    sys.path.insert(0, str(ROOT))
    svg = build_svg()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    print("wrote %s (%d bytes)" % (OUT, len(svg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
