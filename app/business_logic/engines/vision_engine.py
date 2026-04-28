"""
Apple Vision first-line extractor.

Component Type: Engine (Algorithm Volatility).
Crops the top portion of the note PNG and runs VNRecognizeTextRequest
via PyObjC to extract the header line. No I/O beyond reading the PNG.
Encapsulates the Vision framework interaction and region selection logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class IVisionEngine(ABC):

    @abstractmethod
    def extract_first_line(self, png_path: Path) -> str | None:
        """
        Returns the topmost text line from the note image, or None if
        Vision cannot detect any text in the header region.
        """


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class VisionEngine(IVisionEngine):
    """
    Scans the top 20% of the note PNG with Apple Vision text recognition.

    Component Type: Engine (Algorithm Volatility).
    Uses VNRecognizeTextRequest (accurate mode) via PyObjC. Sorts recognised
    observations by vertical position and returns the topmost line.
    Requires: pyobjc-framework-Vision, pyobjc-framework-Quartz.
    """

    # Fraction of image height used as the header scan region.
    _HEADER_FRACTION = 0.20

    def extract_first_line(self, png_path: Path) -> str | None:
        # Late import: Vision framework is macOS-only; keeps import errors isolated.
        try:
            import Quartz
            import Vision
        except ImportError:
            raise RuntimeError(
                "pyobjc-framework-Vision and pyobjc-framework-Quartz are required. "
                "Install with: pip install pyobjc-framework-Vision pyobjc-framework-Quartz"
            )

        cropped_path = self._crop_header(png_path)
        text = self._run_vision(cropped_path, Vision, Quartz)
        cropped_path.unlink(missing_ok=True)
        return text

    def _crop_header(self, png_path: Path) -> Path:
        """Crops the top _HEADER_FRACTION of the image to a temp file."""
        with Image.open(png_path) as img:
            w, h        = img.size
            crop_height = max(1, int(h * self._HEADER_FRACTION))
            cropped     = img.crop((0, 0, w, crop_height))
            tmp_path    = png_path.with_suffix(".header_crop.png")
            cropped.save(tmp_path)
        return tmp_path

    @staticmethod
    def _run_vision(png_path: Path, Vision, Quartz) -> str | None:
        """Runs VNRecognizeTextRequest on png_path and returns the topmost string."""
        url     = Quartz.CFURL.fileURLWithPath_(str(png_path))
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})

        results: list[tuple[float, str]] = []

        def completion(request, error):
            if error:
                return
            for obs in request.results():
                candidate = obs.topCandidates_(1)
                if candidate:
                    # minY gives vertical position; lower minY = higher on page.
                    results.append((obs.boundingBox().origin.y, candidate[0].string()))

        request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(completion)
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)

        handler.performRequests_error_([request], None)

        if not results:
            return None

        # The topmost observation has the highest y value in Vision's flipped coordinate system.
        results.sort(key=lambda r: r[0], reverse=True)
        return results[0][1].strip() or None
