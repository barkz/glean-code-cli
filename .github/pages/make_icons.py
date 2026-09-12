#!/usr/bin/env python3
"""Generate the site's browser icons: a shell prompt in the wordmark's cyan.

An SVG favicon covers every current browser and stays sharp at any size.
iOS home-screen icons must be raster, so a 180x180 PNG is written too --
encoded here with zlib and struct rather than Pillow, keeping the repo's
zero-dependency rule. iOS rounds and masks the corners itself, so the PNG is
drawn square while the SVG carries its own rounded plate.

Regenerate after changing the artwork:
    python3 .github/pages/make_icons.py

tests/test_pages_build.py fails if the committed icons have drifted.
"""

import pathlib
import struct
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SVG_OUT = ROOT / "assets" / "favicon.svg"
PNG_OUT = ROOT / "assets" / "apple-touch-icon.png"

PLATE = (0x1B, 0x1B, 0x23)
MARK = (0x1C, 0xC8, 0xF0)
PNG_SIZE = 180

# Artwork in a 32-unit grid: a ">" chevron and an "_" cursor.
CHEVRON = ((10.0, 10.0), (17.0, 16.0), (10.0, 22.0))
STROKE_HALF = 1.6
CURSOR = (18.6, 20.4, 26.0, 23.0)  # x0, y0, x1, y1


def svg():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32"'
        ' role="img" aria-label="glean_code_cli">\n'
        '  <rect width="32" height="32" rx="7" fill="#%02x%02x%02x"/>\n' % PLATE
        + '  <path d="M%g %g L%g %g L%g %g" fill="none" stroke="#%02x%02x%02x"'
        ' stroke-width="%g" stroke-linecap="square" stroke-linejoin="miter"/>\n'
        % (CHEVRON[0][0], CHEVRON[0][1], CHEVRON[1][0], CHEVRON[1][1],
           CHEVRON[2][0], CHEVRON[2][1], MARK[0], MARK[1], MARK[2], STROKE_HALF * 2)
        + '  <rect x="%g" y="%g" width="%g" height="%g" fill="#%02x%02x%02x"/>\n'
        % (CURSOR[0], CURSOR[1], CURSOR[2] - CURSOR[0], CURSOR[3] - CURSOR[1],
           MARK[0], MARK[1], MARK[2])
        + "</svg>\n"
    )


def _distance_to_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    t = 0.0 if span == 0 else ((px - ax) * dx + (py - ay) * dy) / span
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _coverage(u, v, edge):
    """How much of the pixel at grid point (u, v) the mark covers, 0..1."""
    inside_cursor = (CURSOR[0] <= u <= CURSOR[2]) and (CURSOR[1] <= v <= CURSOR[3])
    if inside_cursor:
        return 1.0
    nearest = min(
        _distance_to_segment(u, v, CHEVRON[0][0], CHEVRON[0][1], CHEVRON[1][0], CHEVRON[1][1]),
        _distance_to_segment(u, v, CHEVRON[1][0], CHEVRON[1][1], CHEVRON[2][0], CHEVRON[2][1]),
    )
    # linear ramp across one pixel for a clean edge
    return max(0.0, min(1.0, (STROKE_HALF - nearest) / edge + 0.5))


def png_rows(size=PNG_SIZE):
    scale = size / 32.0
    edge = 1.0 / scale
    rows = []
    for y in range(size):
        v = (y + 0.5) / scale
        row = bytearray()
        for x in range(size):
            u = (x + 0.5) / scale
            alpha = _coverage(u, v, edge)
            for channel in range(3):
                base, mark = PLATE[channel], MARK[channel]
                row.append(int(round(base + (mark - base) * alpha)))
        rows.append(bytes(row))
    return rows


def _chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def png(size=PNG_SIZE):
    raw = b"".join(b"\x00" + row for row in png_rows(size))
    return b"".join([
        b"\x89PNG\r\n\x1a\n",
        _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)),
        _chunk(b"IDAT", zlib.compress(raw, 9)),
        _chunk(b"IEND", b""),
    ])


def main():
    SVG_OUT.write_text(svg(), encoding="utf-8")
    PNG_OUT.write_bytes(png())
    print("wrote %s and %s (%d bytes)" % (SVG_OUT.name, PNG_OUT.name, PNG_OUT.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
