"""
Vault file resource access.

Component Type: ResourceAccess (Storage Volatility).
Dumb CRUD over vault directories. Reads _slate-config.md, writes to ingest/,
writes pending notes. No business logic — callers decide what to write.
"""

from __future__ import annotations

import re
import yaml
from abc import ABC, abstractmethod
from pathlib import Path

from app.utilities.models import (
    DiagramConfig,
    TypeDefinition,
    VaultRules,
)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class IVaultAccess(ABC):

    @abstractmethod
    def read_rules(self, vault_path: Path) -> VaultRules:
        """Reads and parses _slate-config.md from vault_path root."""

    @abstractmethod
    def write_ingest(self, vault_path: Path, content: str, filename: str) -> Path:
        """Writes content to {vault_path}/ingest/{filename}. Returns the written path."""

    @abstractmethod
    def write_pending(self, pending_dir: Path, content: str, filename: str) -> Path:
        """Writes content to pending_dir/{filename}. Returns the written path."""


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class VaultAccess(IVaultAccess):
    """
    Vault directory I/O.

    Component Type: ResourceAccess (Storage Volatility).
    Abstracts filesystem paths. Parses the _slate-config.md YAML fences
    into VaultRules. No validation logic — that belongs in ValidationEngine.
    """

    _CONFIG_FILE = "_slate-config.md"

    def read_rules(self, vault_path: Path) -> VaultRules:
        config_path = vault_path / self._CONFIG_FILE
        if not config_path.exists():
            raise FileNotFoundError(f"_slate-config.md not found in {vault_path}")
        text = config_path.read_text(encoding="utf-8")
        return self._parse_rules(text)

    def write_ingest(self, vault_path: Path, content: str, filename: str) -> Path:
        ingest_dir = vault_path / "ingest"
        ingest_dir.mkdir(parents=True, exist_ok=True)
        out = ingest_dir / filename
        out.write_text(content, encoding="utf-8")
        return out

    def write_pending(self, pending_dir: Path, content: str, filename: str) -> Path:
        pending_dir.mkdir(parents=True, exist_ok=True)
        out = pending_dir / filename
        out.write_text(content, encoding="utf-8")
        return out

    # ------------------------------------------------------------------
    # Private parsing helpers
    # ------------------------------------------------------------------

    def _parse_rules(self, text: str) -> VaultRules:
        """Extracts all YAML fences from the markdown and assembles VaultRules."""
        blocks = self._extract_yaml_blocks(text)

        vault_name      = ""
        default_handler = "ollama-gemma"
        accepted_types:   list[str]                    = []
        type_definitions: dict[str, TypeDefinition]    = {}
        diagram_types:    dict[str, DiagramConfig]     = {}

        for block in blocks:
            data = yaml.safe_load(block) or {}

            if "vault_name" in data:
                vault_name      = data["vault_name"]
                default_handler = data.get("default_handler", default_handler)

            if "accepted_types" in data:
                accepted_types = data["accepted_types"]

            if "doc_type" in data:
                doc_type = data["doc_type"]
                type_definitions[doc_type] = TypeDefinition(
                    doc_type          = doc_type,
                    required_fields   = data.get("required_fields", []),
                    optional_fields   = data.get("optional_fields", []),
                    triggers_workflow = data.get("triggers_workflow", False),
                    workflow_dir      = data.get("workflow_dir"),
                )

            if "diagram_type" in data:
                name = data["diagram_type"]
                diagram_types[name] = DiagramConfig(
                    format           = data.get("format", "mermaid"),
                    allowed_elements = data.get("allowed_elements", []),
                )

        return VaultRules(
            vault_name       = vault_name,
            default_handler  = default_handler,
            accepted_types   = accepted_types,
            type_definitions = type_definitions,
            diagram_types    = diagram_types,
        )

    @staticmethod
    def _extract_yaml_blocks(text: str) -> list[str]:
        return re.findall(r"```yaml\s*(.*?)```", text, re.DOTALL)
