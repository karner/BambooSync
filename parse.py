"""
Parse Wacom Bamboo Slate WILL 2.0 stroke data and render to PNG.

Usage:
  python parse.py downloads/drawing_*.bin
"""

import sys
from collections import namedtuple
from pathlib import Path
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Packet identification
# ---------------------------------------------------------------------------

FILE_MAGIC = bytes([0x62, 0x38, 0x62, 0x74])

Point = namedtuple('Point', ['x', 'y', 'p'])


def _nbytes(header: int) -> int:
    return bin(header).count('1')


def identify(data: list) -> str:
    h = data[0]
    nb = _nbytes(h)
    payload = data[1:1 + nb]

    if data[0:4] == [0x62, 0x38, 0x62, 0x74]:
        return 'FILE_HEADER'
    if data[0:7] == [0xfc, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff]:
        return 'STROKE_END'
    if payload == [0xff] * nb and nb == 8:
        return 'EOF'
    if h & 0x3 == 0:
        return 'DELTA'
    if not payload:
        return 'UNKNOWN'
    if payload[0:3] == [0xff, 0xee, 0xee]:
        return 'STROKE_HEADER'
    if payload[0:2] == [0xff, 0xff]:
        return 'POINT'
    return 'UNKNOWN'


# ---------------------------------------------------------------------------
# Packet parsers — return (size_consumed, fields_dict)
# ---------------------------------------------------------------------------

def parse_file_header(data: list) -> int:
    return 4  # magic only, no extra fields for Spark/Slate format


def parse_stroke_header(data: list) -> int:
    nb = _nbytes(data[0])
    return 1 + nb


def parse_stroke_end(data: list) -> int:
    nb = _nbytes(data[0])
    return 1 + nb


def parse_eof(data: list) -> int:
    nb = _nbytes(data[0])
    return 1 + nb


def _extract_delta(mask: int, databytes: list) -> tuple:
    """Return (abs_value, delta, bytes_consumed). Either abs or delta will be None."""
    if mask == 0:
        return None, None, 0
    if mask == 2:
        delta = int.from_bytes(bytes([databytes[0]]), byteorder='little', signed=True)
        return None, delta, 1
    if mask == 3:
        value = databytes[0] + (databytes[1] << 8)
        return value, None, 2
    raise ValueError(f'Unexpected mask {mask}')


def parse_delta(header: int, data: list) -> tuple:
    """Parse a DELTA packet. Returns (x, dx, y, dy, p, dp, size)."""
    xmask = (header & 0b00001100) >> 2
    ymask = (header & 0b00110000) >> 4
    pmask = (header & 0b11000000) >> 6

    offset = 1
    x, dx, s = _extract_delta(xmask, data[offset:])
    offset += s
    y, dy, s = _extract_delta(ymask, data[offset:])
    offset += s
    p, dp, s = _extract_delta(pmask, data[offset:])
    offset += s

    return x, dx, y, dy, p, dp, offset


def parse_point(data: list) -> tuple:
    """A POINT wraps a DELTA with a [0xff, 0xff] header — strip them first."""
    header = data[0] & ~0x3  # clear lowest 2 bits for DELTA parsing
    payload = data[3:]       # skip original header + [0xff, 0xff]
    x, dx, y, dy, p, dp, inner_size = parse_delta(header, [header] + payload)
    return x, dx, y, dy, p, dp, 1 + 2 + inner_size - 1  # header + ff ff + delta payload


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_strokes(raw: bytes) -> list[list[Point]]:
    data = list(raw)

    if data[0:4] != list(FILE_MAGIC):
        raise ValueError(f'Unknown file magic: {bytes(data[:4]).hex()}')

    data = data[4:]  # consume file header

    strokes = []
    points = []
    last_point = Point(0, 0, 0)
    last_delta = Point(0, 0, 0)

    while data:
        ptype = identify(data)

        if ptype == 'FILE_HEADER':
            break

        elif ptype == 'STROKE_HEADER':
            if points:
                strokes.append(points)
            points = []
            last_delta = Point(0, 0, 0)
            size = parse_stroke_header(data)
            data = data[size:]

        elif ptype == 'STROKE_END':
            if points:
                strokes.append(points)
            points = []
            size = parse_stroke_end(data)
            data = data[size:]

        elif ptype == 'EOF':
            if points:
                strokes.append(points)
            size = parse_eof(data)
            data = data[size:]
            break

        elif ptype in ('DELTA', 'POINT'):
            if ptype == 'POINT':
                x, dx, y, dy, p, dp, size = parse_point(data)
            else:
                x, dx, y, dy, p, dp, size = parse_delta(data[0], data)

            cdx, cdy, cdp = last_delta
            ax, ay, ap = last_point

            if dx is not None:
                cdx += dx
            elif x is not None:
                ax = x
                cdx = 0

            if dy is not None:
                cdy += dy
            elif y is not None:
                ay = y
                cdy = 0

            if dp is not None:
                cdp += dp
            elif p is not None:
                ap = p
                cdp = 0

            last_delta = Point(cdx, cdy, cdp)
            last_point = Point(ax + cdx, ay + cdy, ap + cdp)
            points.append(last_point)
            data = data[size:]

        else:  # UNKNOWN — skip 1 + nbytes
            nb = _nbytes(data[0])
            data = data[1 + nb:]

    return strokes


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render(strokes: list[list[Point]], out_path: Path, px: int = 2480):
    """Render strokes to a white PNG. px = width in pixels (A4 at 300dpi)."""
    if not strokes:
        print("No strokes to render.")
        return

    all_pts = [p for s in strokes for p in s]
    xs = [p.x for p in all_pts]
    ys = [p.y for p in all_pts]
    ps = [p.p for p in all_pts]

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    p_max = max(ps) or 1

    span_x = x_max - x_min or 1
    span_y = y_max - y_min or 1
    aspect = span_y / span_x
    py = int(px * aspect)

    print(f"  Bounding box: x={x_min}..{x_max}, y={y_min}..{y_max}, p_max={p_max}")
    print(f"  Canvas: {px}×{py}px, {len(strokes)} stroke(s), {len(all_pts)} points")

    img = Image.new('RGB', (px, py), 'white')
    draw = ImageDraw.Draw(img)

    margin = 0.05
    def tx(x): return int((x - x_min) / span_x * px * (1 - 2*margin) + px * margin)
    def ty(y): return int((y - y_min) / span_y * py * (1 - 2*margin) + py * margin)

    for stroke in strokes:
        if len(stroke) < 2:
            continue
        for i in range(len(stroke) - 1):
            a, b = stroke[i], stroke[i + 1]
            pressure = (a.p + b.p) / 2
            width = max(1, int(pressure / p_max * 6))
            draw.line([(tx(a.x), ty(a.y)), (tx(b.x), ty(b.y))],
                      fill='black', width=width)

    img.save(out_path)
    print(f"  Saved → {out_path}")


# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python parse.py <drawing.bin> [...]")
        sys.exit(1)

    for arg in sys.argv[1:]:
        path = Path(arg)
        print(f"\nParsing {path.name} ({path.stat().st_size} bytes)...")
        raw = path.read_bytes()
        strokes = parse_strokes(raw)
        print(f"  Decoded {len(strokes)} stroke(s)")
        out = path.with_suffix('.png')
        render(strokes, out)
