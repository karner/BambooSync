"""
WILL 2.0 stroke parser.

Component Type: Engine (Algorithm Volatility).
Pure function — accepts raw WILL 2.0 bytes, returns stroke point arrays.
No I/O, no state, no events. Encapsulates the Wacom binary decode algorithm.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.utilities.models import Point


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class IStrokeParseEngine(ABC):

    @abstractmethod
    def parse(self, raw: bytes) -> list[list[Point]]:
        """Decodes raw WILL 2.0 bytes into a list of strokes (each a list of Points)."""


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class StrokeParseEngine(IStrokeParseEngine):
    """
    Decodes the Wacom WILL 2.0 binary format.

    Component Type: Engine (Algorithm Volatility).
    Pure function. Encapsulates delta/absolute coordinate reconstruction
    and the file-header / stroke-boundary token detection.
    """

    _FILE_MAGIC = bytes([0x62, 0x38, 0x62, 0x74])

    def parse(self, raw: bytes) -> list[list[Point]]:
        if raw[:4] != self._FILE_MAGIC:
            raise ValueError(f"Unknown WILL 2.0 magic: {raw[:4].hex()}")
        data = list(raw[4:])
        strokes: list[list[Point]] = []
        points:  list[Point]       = []
        last_abs   = Point(0, 0, 0)
        last_delta = Point(0, 0, 0)

        while data:
            token = self._identify(data)

            if token in ("STROKE_HEADER", "STROKE_END"):
                if points:
                    strokes.append(points)
                points     = []
                last_delta = Point(0, 0, 0)
                data       = data[1 + self._nbits(data[0]):]

            elif token == "EOF":
                if points:
                    strokes.append(points)
                break

            elif token in ("DELTA", "POINT"):
                last_abs, last_delta, size = self._apply_delta(token, data, last_abs, last_delta)
                points.append(last_abs)
                data = data[size:]

            else:
                data = data[1 + self._nbits(data[0]):]

        return strokes

    # ------------------------------------------------------------------

    @staticmethod
    def _nbits(b: int) -> int:
        return bin(b).count("1")

    def _identify(self, data: list) -> str:
        nb      = self._nbits(data[0])
        payload = data[1:1 + nb]

        if data[0:4] == [0x62, 0x38, 0x62, 0x74]:
            return "FILE_HEADER"
        if data[0:7] == [0xFC, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]:
            return "STROKE_END"
        if payload == [0xFF] * nb and nb == 8:
            return "EOF"
        if data[0] & 0x3 == 0:
            return "DELTA"
        if not payload:
            return "UNKNOWN"
        if payload[0:3] == [0xFF, 0xEE, 0xEE]:
            return "STROKE_HEADER"
        if payload[0:2] == [0xFF, 0xFF]:
            return "POINT"
        return "UNKNOWN"

    @staticmethod
    def _extract_axis(mask: int, data: list) -> tuple[int | None, int | None, int]:
        if mask == 0:
            return None, None, 0
        if mask == 2:
            return None, int.from_bytes(bytes([data[0]]), signed=True), 1
        if mask == 3:
            return data[0] + (data[1] << 8), None, 2
        raise ValueError(f"Bad mask {mask}")

    def _parse_delta_record(self, header: int, data: list) -> tuple:
        off = 1
        x, dx, s = self._extract_axis((header >> 2) & 3, data[off:]); off += s
        y, dy, s = self._extract_axis((header >> 4) & 3, data[off:]); off += s
        p, dp, s = self._extract_axis((header >> 6) & 3, data[off:]); off += s
        return x, dx, y, dy, p, dp, off

    def _apply_delta(
        self,
        token:      str,
        data:       list,
        last_abs:   Point,
        last_delta: Point,
    ) -> tuple[Point, Point, int]:
        if token == "POINT":
            h = data[0] & ~0x3
            x, dx, y, dy, p, dp, inner = self._parse_delta_record(h, [h] + data[3:])
            size = 1 + 2 + inner - 1
        else:
            x, dx, y, dy, p, dp, size = self._parse_delta_record(data[0], data)

        cdx, cdy, cdp = last_delta.x, last_delta.y, last_delta.p
        ax,  ay,  ap  = last_abs.x,   last_abs.y,   last_abs.p

        if dx is not None:
            cdx += dx
        elif x is not None:
            ax, cdx = x, 0

        if dy is not None:
            cdy += dy
        elif y is not None:
            ay, cdy = y, 0

        if dp is not None:
            cdp += dp
        elif p is not None:
            ap, cdp = p, 0

        new_delta = Point(cdx, cdy, cdp)
        new_abs   = Point(ax + cdx, ay + cdy, ap + cdp)
        return new_abs, new_delta, size
