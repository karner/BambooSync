"""
Stroke renderer.

Component Type: Engine (Algorithm Volatility).
Pure function — accepts stroke point arrays, writes a PNG.
Encapsulates coordinate normalisation and pressure-to-width mapping.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image, ImageDraw

from app.utilities.models import Point


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class IRenderEngine(ABC):

    @abstractmethod
    def render(self, strokes: list[list[Point]], out_path: Path, width_px: int = 2480) -> bool:
        """
        Renders strokes to a PNG at out_path.
        Returns False and skips output if strokes contain no points.
        """


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class RenderEngine(IRenderEngine):
    """
    Renders WILL 2.0 stroke arrays to a high-contrast black-on-white PNG.

    Component Type: Engine (Algorithm Volatility).
    Normalises coordinates to the canvas, maps pressure to line width,
    rotates 90° to match physical paper orientation. Pure algorithm.
    """

    _MARGIN        = 0.05   # fractional canvas margin on each side
    _MAX_LINE_W    = 6      # maximum line width in pixels at full pressure
    _ROTATION_DEG  = -90    # Slate stores strokes rotated; this corrects orientation

    def render(self, strokes: list[list[Point]], out_path: Path, width_px: int = 2480) -> bool:
        all_pts = [p for s in strokes for p in s]
        if not all_pts:
            return False

        xs   = [p.x for p in all_pts]
        ys   = [p.y for p in all_pts]
        p_max = max(p.p for p in all_pts) or 1

        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        span_x = x_max - x_min or 1
        span_y = y_max - y_min or 1

        height_px = int(width_px * span_y / span_x)

        def tx(x: int) -> int:
            return int((x - x_min) / span_x * width_px * (1 - 2 * self._MARGIN) + width_px * self._MARGIN)

        def ty(y: int) -> int:
            return int((y - y_min) / span_y * height_px * (1 - 2 * self._MARGIN) + height_px * self._MARGIN)

        img  = Image.new("RGB", (width_px, height_px), "white")
        draw = ImageDraw.Draw(img)

        for stroke in strokes:
            if len(stroke) < 2:
                continue
            for a, b in zip(stroke, stroke[1:]):
                pressure = (a.p + b.p) / 2
                width    = max(1, int(pressure / p_max * self._MAX_LINE_W))
                draw.line([(tx(a.x), ty(a.y)), (tx(b.x), ty(b.y))], fill="black", width=width)

        img.rotate(self._ROTATION_DEG, expand=True).save(out_path)
        return True
