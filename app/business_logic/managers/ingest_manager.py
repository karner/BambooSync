"""
Note ingest manager.

Component Type: Manager (Workflow Volatility).
Orchestrates the classification, validation, transcription, and vault
write pipeline for a single note PNG. Knows *when* each step runs;
delegates *how* to engines and *where* to resource access.
Queued by SyncManager after a successful download.
"""

from __future__ import annotations

import textwrap
import time
from abc import ABC, abstractmethod
from pathlib import Path

from app.business_logic.engines.diagram_engine      import IDiagramEngine
from app.business_logic.engines.transcription_engine import ITranscriptionEngine
from app.business_logic.engines.validation_engine   import IValidationEngine
from app.business_logic.engines.vision_engine       import IVisionEngine
from app.resource_access.vault_access               import IVaultAccess
from app.utilities.config                           import pending_dir, resolve_vault_path, unrouted_dir
from app.utilities.event_bus                        import (
    EventBus,
    NoteIngestedEvent,
    NoteIngestFailedEvent,
    StatusUpdateEvent,
)
from app.utilities.models                           import IngestResult, NoteHeader, VaultRules


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class IIngestManager(ABC):

    @abstractmethod
    async def process_note(self, png_path: Path, timestamp: int) -> IngestResult:
        """
        Classifies, validates, transcribes, and routes a single note PNG.
        Writes output to the vault ingest directory or generates a follow-up subtask.
        """


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class IngestManager(IIngestManager):
    """
    Orchestrates the note classification and routing workflow.

    Component Type: Manager (Workflow Volatility).
    Sequence: Vision extract → vault load → validate → transcribe/diagram → write.
    On incomplete notes: write pending file + write missing-info subtask to vault.
    Publishes NoteIngestedEvent or NoteIngestFailedEvent on completion.
    """

    def __init__(
        self,
        vision_engine:       IVisionEngine,
        validation_engine:   IValidationEngine,
        transcription_engine: ITranscriptionEngine,
        diagram_engine:      IDiagramEngine,
        vault_access:        IVaultAccess,
        event_bus:           EventBus,
    ) -> None:
        if vision_engine is None:
            raise ValueError("vision_engine must not be None")
        if validation_engine is None:
            raise ValueError("validation_engine must not be None")
        if transcription_engine is None:
            raise ValueError("transcription_engine must not be None")
        if diagram_engine is None:
            raise ValueError("diagram_engine must not be None")
        if vault_access is None:
            raise ValueError("vault_access must not be None")
        if event_bus is None:
            raise ValueError("event_bus must not be None")

        self.m_vision_engine        = vision_engine
        self.m_validation_engine    = validation_engine
        self.m_transcription_engine = transcription_engine
        self.m_diagram_engine       = diagram_engine
        self.m_vault_access         = vault_access
        self.m_event_bus            = event_bus

    async def process_note(self, png_path: Path, timestamp: int) -> IngestResult:
        label = time.strftime("%Y%m%d_%H%M%S", time.gmtime(timestamp))

        await self.m_event_bus.publish(StatusUpdateEvent(f"Ingesting {label}..."))

        # 1. Extract header line.
        first_line = self.m_vision_engine.extract_first_line(png_path)
        if not first_line:
            return await self._quarantine(png_path, label, "Vision returned no text")

        # 2. Parse vault name + doc type.
        header = self._parse_header(first_line)
        if header is None:
            return await self._quarantine(png_path, label, f"Unparseable header: '{first_line}'")

        # 3. Resolve vault path.
        vault_path = resolve_vault_path(header.vault_name)
        if vault_path is None:
            return await self._quarantine(
                png_path, label, f"No VAULT_{header.vault_name}_PATH env var"
            )

        # 4. Load vault rules.
        rules: VaultRules = self.m_vault_access.read_rules(vault_path)

        # 5. Validate completeness.
        result = self.m_validation_engine.validate(header, rules)
        if not result.is_valid:
            return await self._handle_incomplete(png_path, label, header, vault_path, result.missing_fields)

        # 6. Transcribe (or convert diagram).
        handler_name = rules.default_handler
        if header.doc_type == "DIAGRAM":
            diagram_type   = header.fields.get("type", "")
            diagram_config = rules.diagram_types.get(diagram_type)
            body = self.m_diagram_engine.transcribe_diagram(png_path, diagram_config, handler_name)
        else:
            body = self.m_transcription_engine.transcribe(png_path, handler_name)

        # 7. Write to vault ingest.
        content   = self._format_ingest_note(header, body or "", timestamp)
        filename  = f"{label}_{header.doc_type}.md"
        out_path  = self.m_vault_access.write_ingest(vault_path, content, filename)

        await self.m_event_bus.publish(NoteIngestedEvent(
            vault_name  = header.vault_name,
            doc_type    = header.doc_type,
            output_path = str(out_path),
        ))
        return IngestResult(
            png_path    = str(png_path),
            doc_type    = header.doc_type,
            vault_name  = header.vault_name,
            output_path = str(out_path),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_header(first_line: str) -> NoteHeader | None:
        """Parses 'VAULT_NAME  DOC_TYPE  [KEY=value ...]' into a NoteHeader."""
        tokens = first_line.strip().split()
        if len(tokens) < 2:
            return None
        vault_name = tokens[0].upper()
        doc_type   = tokens[1].upper()
        fields: dict[str, str] = {}
        for token in tokens[2:]:
            if "=" in token:
                key, _, val = token.partition("=")
                fields[key.lower()] = val
        return NoteHeader(vault_name=vault_name, doc_type=doc_type, fields=fields)

    async def _quarantine(self, png_path: Path, label: str, reason: str) -> IngestResult:
        dest = unrouted_dir() / png_path.name
        png_path.rename(dest)
        await self.m_event_bus.publish(NoteIngestFailedEvent(png_path=str(png_path), reason=reason))
        return IngestResult(png_path=str(png_path), doc_type="UNKNOWN", vault_name="")

    async def _handle_incomplete(
        self,
        png_path:       Path,
        label:          str,
        header:         NoteHeader,
        vault_path:     Path,
        missing_fields: list[str],
    ) -> IngestResult:
        # Hold partial note in pipeline pending dir.
        pending_filename = f"{label}_partial.md"
        pending_content  = self._format_pending_note(header, png_path, missing_fields)
        pending_path     = self.m_vault_access.write_pending(
            pending_dir(), pending_content, pending_filename
        )

        # Write actionable subtask to vault ingest.
        subtask_filename = f"{label}_missing-info.md"
        subtask_content  = self._format_missing_info_subtask(
            header, str(pending_path), label, missing_fields
        )
        out_path = self.m_vault_access.write_ingest(vault_path, subtask_content, subtask_filename)

        await self.m_event_bus.publish(NoteIngestFailedEvent(
            png_path = str(png_path),
            reason   = f"Missing fields: {', '.join(missing_fields)}",
        ))
        return IngestResult(
            png_path    = str(png_path),
            doc_type    = header.doc_type,
            vault_name  = header.vault_name,
            output_path = str(out_path),
            is_pending  = True,
        )

    @staticmethod
    def _format_ingest_note(header: NoteHeader, body: str, timestamp: int) -> str:
        created = time.strftime("%Y-%m-%d %H:%M", time.gmtime(timestamp))
        field_lines = "\n".join(f"{k}: {v}" for k, v in header.fields.items())
        return textwrap.dedent(f"""\
            ---
            type: {header.doc_type}
            vault: {header.vault_name}
            created: {created}
            source: bamboo-slate
            {field_lines}
            ---

            {body}
        """)

    @staticmethod
    def _format_pending_note(header: NoteHeader, png_path: Path, missing: list[str]) -> str:
        return textwrap.dedent(f"""\
            ---
            type: PENDING
            vault: {header.vault_name}
            doc_type: {header.doc_type}
            source_image: {png_path}
            missing_fields: [{", ".join(missing)}]
            ---
        """)

    @staticmethod
    def _format_missing_info_subtask(
        header:       NoteHeader,
        pending_path: str,
        label:        str,
        missing:      list[str],
    ) -> str:
        checklist = "\n".join(f"- [ ] `{f}`" for f in missing)
        return textwrap.dedent(f"""\
            ---
            type: MISSING_INFO
            original: {pending_path}
            created: {label}
            vault: {header.vault_name}
            doc_type: {header.doc_type}
            ---

            ## Missing fields for {header.doc_type}

            {checklist}

            Resolve by writing a TASK_UPDATE note referencing the original, \
            or editing the _pending file directly and re-triggering.
        """)
