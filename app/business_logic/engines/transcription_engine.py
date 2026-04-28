"""
AI transcription engine.

Component Type: Engine (Algorithm Volatility).
Constructs prompts and delegates to a named AI handler from the registry.
Encapsulates prompt design for plain transcription. No transport logic —
that lives in handler implementations inside HandlerRegistry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.utilities.handler_registry import HandlerRegistry


_TRANSCRIPTION_PROMPT = (
    "Transcribe all handwritten text in this image exactly as written. "
    "Preserve line breaks. Output only the transcribed text."
)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class ITranscriptionEngine(ABC):

    @abstractmethod
    def transcribe(self, png_path: Path, handler_name: str) -> str | None:
        """
        Transcribes the full body of a note image.
        Returns the transcribed text or None if the backend fails.
        """


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class TranscriptionEngine(ITranscriptionEngine):
    """
    Builds the transcription prompt and calls the configured AI handler.

    Component Type: Engine (Algorithm Volatility).
    Resolves the handler by name from the registry. Keeps prompt logic
    isolated from transport — changing the prompt does not touch the handler.
    """

    def __init__(self, registry: HandlerRegistry) -> None:
        if registry is None:
            raise ValueError("registry must not be None")
        self.m_registry = registry

    def transcribe(self, png_path: Path, handler_name: str) -> str | None:
        if not png_path:
            raise ValueError("png_path must not be None")
        if not handler_name:
            raise ValueError("handler_name must not be empty")

        handler = self.m_registry.get(handler_name)
        return handler.transcribe(png_path, _TRANSCRIPTION_PROMPT)
