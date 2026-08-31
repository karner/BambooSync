"""
CLI entry point — one-shot headless sync.

Connects to the Slate, processes all stored notes through the full pipeline,
and exits. No GUI. Useful for testing and scripted use.

For the menu bar app run: python main.py
"""

import asyncio
import sys

from app.business_logic.engines.diagram_engine       import DiagramEngine
from app.business_logic.engines.render_engine        import RenderEngine
from app.business_logic.engines.stroke_parse_engine  import StrokeParseEngine
from app.business_logic.engines.transcription_engine import TranscriptionEngine
from app.business_logic.engines.validation_engine    import ValidationEngine
from app.business_logic.engines.vision_engine        import VisionEngine
from app.business_logic.managers.ingest_manager      import IngestManager
from app.business_logic.managers.sync_manager        import SyncManager
from app.resource_access.slate_access                import SlateAccess
from app.resource_access.vault_access                import VaultAccess
from app.utilities.config                            import load_config
from app.utilities.event_bus                         import (
    EventBus,
    StatusUpdateEvent,
    SyncCompletedEvent,
    SyncFailedEvent,
    NoteIngestedEvent,
    NoteIngestFailedEvent,
)
from app.utilities.handler_registry                  import HandlerRegistry, OllamaHandler
from app.utilities.settings                          import Settings


def _print_handler(event):
    if isinstance(event, StatusUpdateEvent):
        print(f"  {event.message}")
    elif isinstance(event, SyncCompletedEvent):
        print(f"Done — {event.synced_count} note(s) synced.")
    elif isinstance(event, SyncFailedEvent):
        print(f"Sync failed: {event.reason}", file=sys.stderr)
    elif isinstance(event, NoteIngestedEvent):
        print(f"  → {event.doc_type} written to {event.vault_name}/ingest/")
    elif isinstance(event, NoteIngestFailedEvent):
        print(f"  ! Ingest failed: {event.reason}", file=sys.stderr)


def _build_manager() -> SyncManager:
    cfg     = load_config()
    host_id = bytes.fromhex(cfg["host"]["id"])

    event_bus = EventBus()
    for event_type in (
        StatusUpdateEvent,
        SyncCompletedEvent,
        SyncFailedEvent,
        NoteIngestedEvent,
        NoteIngestFailedEvent,
    ):
        event_bus.subscribe(event_type, _print_handler)

    registry = HandlerRegistry()
    registry.register("ollama-moondream", OllamaHandler(model="moondream"))
    registry.register("ollama-gemma",     OllamaHandler(model="gemma4:26b"))

    vault_access = VaultAccess()

    ingest_manager = IngestManager(
        vision_engine        = VisionEngine(),
        validation_engine    = ValidationEngine(),
        transcription_engine = TranscriptionEngine(registry=registry),
        diagram_engine       = DiagramEngine(registry=registry),
        vault_access         = vault_access,
        event_bus            = event_bus,
    )

    return SyncManager(
        slate_access   = SlateAccess(host_id=host_id),
        parse_engine   = StrokeParseEngine(),
        render_engine  = RenderEngine(),
        ingest_manager = ingest_manager,
        event_bus      = event_bus,
        settings       = Settings(),
    )


async def _run() -> int:
    manager = _build_manager()
    result  = await manager.sync_all()
    if result.errors:
        for err in result.errors:
            print(f"  error: {err}", file=sys.stderr)
    return 0 if result.failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
