"""
AI handler registry.

Component Type: Utility (Cross-cutting).
Registers and resolves named AI backends. Adding a new backend requires
implementing IAIHandler and registering it — no changes to pipeline code.
"""

from __future__ import annotations

import base64
import json
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path


# ---------------------------------------------------------------------------
# Handler interface
# ---------------------------------------------------------------------------

class IAIHandler(ABC):
    """Contract for all AI backends."""

    @abstractmethod
    def transcribe(self, png_path: Path, prompt: str) -> str | None:
        """Sends png_path to the backend with prompt. Returns text or None on failure."""


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------

class OllamaHandler(IAIHandler):
    """
    Calls a local Ollama model.

    Component Type: Utility / AI Backend.
    Dumb transport — builds the request, returns the raw response text.
    No prompt logic lives here; callers supply the full prompt.
    """

    def __init__(
        self,
        model:    str,
        base_url: str = "http://localhost:11434",
        timeout:  int = 60,
    ) -> None:
        if not model:
            raise ValueError("model must not be empty")
        self.m_model   = model
        self.m_url     = base_url.rstrip("/") + "/api/generate"
        self.m_timeout = timeout

    def transcribe(self, png_path: Path, prompt: str) -> str | None:
        img_b64 = base64.b64encode(png_path.read_bytes()).decode()
        payload = json.dumps({
            "model":  self.m_model,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
        }).encode()
        try:
            req = urllib.request.Request(
                self.m_url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.m_timeout) as resp:
                return json.loads(resp.read()).get("response", "").strip() or None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class HandlerRegistry:
    """
    Resolves handler names to IAIHandler instances.

    Component Type: Utility (Cross-cutting).
    Populated at startup in main.py. Engines look up handlers by name.
    """

    def __init__(self) -> None:
        self.m_handlers: dict[str, IAIHandler] = {}

    def register(self, name: str, handler: IAIHandler) -> None:
        if not name:
            raise ValueError("Handler name must not be empty")
        if handler is None:
            raise ValueError("Handler must not be None")
        self.m_handlers[name] = handler

    def get(self, name: str) -> IAIHandler:
        handler = self.m_handlers.get(name)
        if handler is None:
            raise KeyError(f"No handler registered for '{name}'")
        return handler

    def names(self) -> list[str]:
        return list(self.m_handlers.keys())
