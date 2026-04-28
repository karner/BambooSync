"""
Shared data models for the bamboo-slate pipeline.

Component Type: Utility (Cross-cutting).
Plain data containers — no logic, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from collections import namedtuple


# ---------------------------------------------------------------------------
# Stroke data (from WILL 2.0 decode)
# ---------------------------------------------------------------------------

Point = namedtuple("Point", ["x", "y", "p"])


# ---------------------------------------------------------------------------
# Status bar states
# ---------------------------------------------------------------------------

class SyncStatus(Enum):
    IDLE     = auto()
    SCANNING = auto()
    SYNCING  = auto()
    ERROR    = auto()


# ---------------------------------------------------------------------------
# Note header (extracted from first line by VisionEngine)
# ---------------------------------------------------------------------------

@dataclass
class NoteHeader:
    vault_name: str
    doc_type:   str
    fields:     dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    is_valid:       bool
    missing_fields: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Vault rules (parsed from _slate-config.md)
# ---------------------------------------------------------------------------

@dataclass
class DiagramConfig:
    format:           str         # "mermaid" or "plantuml"
    allowed_elements: list[str]   = field(default_factory=list)


@dataclass
class TypeDefinition:
    doc_type:          str
    required_fields:   list[str]  = field(default_factory=list)
    optional_fields:   list[str]  = field(default_factory=list)
    triggers_workflow: bool        = False
    workflow_dir:      str | None  = None


@dataclass
class VaultRules:
    vault_name:       str
    default_handler:  str
    accepted_types:   list[str]                    = field(default_factory=list)
    type_definitions: dict[str, TypeDefinition]    = field(default_factory=dict)
    diagram_types:    dict[str, DiagramConfig]      = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline results
# ---------------------------------------------------------------------------

@dataclass
class SyncResult:
    synced_count: int
    failed_count: int
    errors:       list[str] = field(default_factory=list)


@dataclass
class IngestResult:
    png_path:    str
    doc_type:    str
    vault_name:  str
    output_path: str | None = None   # set on success
    is_pending:  bool        = False  # set when validation failed
