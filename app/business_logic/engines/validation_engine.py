"""
Note validation engine.

Component Type: Engine (Algorithm Volatility).
Pure function — checks a parsed note header against the vault rules and
returns a ValidationResult. No I/O, no state, no events.
Encapsulates all field-presence and type-acceptance logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.utilities.models import NoteHeader, ValidationResult, VaultRules


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class IValidationEngine(ABC):

    @abstractmethod
    def validate(self, header: NoteHeader, rules: VaultRules) -> ValidationResult:
        """
        Returns ValidationResult.is_valid = True only when all required fields
        for the header's doc_type are present and the type is accepted by the vault.
        """


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class ValidationEngine(IValidationEngine):
    """
    Validates a NoteHeader against VaultRules.

    Component Type: Engine (Algorithm Volatility).
    Checks type acceptance, required field presence, and diagram sub-type
    validity. Returns a complete list of missing fields so callers can
    generate precise follow-up subtasks.
    """

    def validate(self, header: NoteHeader, rules: VaultRules) -> ValidationResult:
        if header is None:
            raise ValueError("header must not be None")
        if rules is None:
            raise ValueError("rules must not be None")

        missing: list[str] = []

        if header.doc_type not in rules.accepted_types:
            missing.append(f"doc_type '{header.doc_type}' is not accepted by this vault")
            return ValidationResult(is_valid=False, missing_fields=missing)

        type_def = rules.type_definitions.get(header.doc_type)
        if type_def is None:
            missing.append(f"no definition found for doc_type '{header.doc_type}'")
            return ValidationResult(is_valid=False, missing_fields=missing)

        for field in type_def.required_fields:
            if field not in header.fields or not header.fields[field]:
                missing.append(field)

        if header.doc_type == "DIAGRAM":
            diagram_type = header.fields.get("type", "")
            if diagram_type and diagram_type not in rules.diagram_types:
                missing.append(
                    f"diagram type '{diagram_type}' is not defined in _slate-config.md"
                )

        return ValidationResult(is_valid=len(missing) == 0, missing_fields=missing)
