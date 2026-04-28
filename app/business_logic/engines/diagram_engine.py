"""
Diagram transcription engine.

Component Type: Engine (Algorithm Volatility).
Builds an element-restricted prompt from DiagramConfig and delegates
to the AI handler. Encapsulates the constraint-injection logic that
prevents the model from emitting unsupported diagram syntax.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.utilities.handler_registry import HandlerRegistry
from app.utilities.models import DiagramConfig


_PROMPT_TEMPLATE = (
    "Convert the handwritten diagram in this image to {format} syntax.\n"
    "You may ONLY use the following elements — do not introduce any syntax not in this list:\n"
    "{elements}\n\n"
    "Output only the raw {format} code block. No explanation."
)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class IDiagramEngine(ABC):

    @abstractmethod
    def transcribe_diagram(
        self,
        png_path:       Path,
        diagram_config: DiagramConfig,
        handler_name:   str,
    ) -> str | None:
        """
        Converts a handwritten diagram PNG to constrained Mermaid or PlantUML.
        Returns the syntax string or None if the backend fails.
        """


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class DiagramEngine(IDiagramEngine):
    """
    Injects allowed_elements into the AI prompt before calling the handler.

    Component Type: Engine (Algorithm Volatility).
    The element restriction is the algorithm: it constrains the model output
    to the vocabulary defined per diagram type in _slate-config.md.
    Adding a new diagram format requires only a new DiagramConfig entry —
    no code changes.
    """

    def __init__(self, registry: HandlerRegistry) -> None:
        if registry is None:
            raise ValueError("registry must not be None")
        self.m_registry = registry

    def transcribe_diagram(
        self,
        png_path:       Path,
        diagram_config: DiagramConfig,
        handler_name:   str,
    ) -> str | None:
        if not png_path:
            raise ValueError("png_path must not be None")
        if diagram_config is None:
            raise ValueError("diagram_config must not be None")
        if not handler_name:
            raise ValueError("handler_name must not be empty")

        elements_list = "\n".join(f"  - {e}" for e in diagram_config.allowed_elements)
        prompt = _PROMPT_TEMPLATE.format(
            format   = diagram_config.format,
            elements = elements_list,
        )

        handler = self.m_registry.get(handler_name)
        return handler.transcribe(png_path, prompt)
