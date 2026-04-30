"""
Application entry point — composition root.

Wires all components together via constructor injection and starts the
status bar client. No business logic lives here.
"""

from app.business_logic.engines.diagram_engine       import DiagramEngine
from app.business_logic.engines.render_engine        import RenderEngine
from app.business_logic.engines.stroke_parse_engine  import StrokeParseEngine
from app.business_logic.engines.transcription_engine import TranscriptionEngine
from app.business_logic.engines.validation_engine    import ValidationEngine
from app.business_logic.engines.vision_engine        import VisionEngine
from app.business_logic.managers.ingest_manager      import IngestManager
from app.business_logic.managers.sync_manager        import SyncManager
from app.client.status_bar_client                    import StatusBarClient
from app.resource_access.slate_access                import SlateAccess
from app.resource_access.vault_access                import VaultAccess
from app.utilities.config                            import load_config
from app.utilities.event_bus                         import EventBus
from app.utilities.handler_registry                  import HandlerRegistry, OllamaHandler
from app.utilities.settings                          import Settings


def _build_handler_registry(settings: Settings) -> HandlerRegistry:
    registry = HandlerRegistry()
    for h in settings.get_handlers():
        if not h.get("enabled"):
            continue
        name  = h.get("name", "").strip()
        model = h.get("model", "").strip()
        url   = h.get("url", "http://localhost:11434").strip()
        if name and model:
            registry.register(name, OllamaHandler(model=model, base_url=url))
    if not registry.names():
        # Ensure at least one handler so the app can start.
        registry.register("ollama-gemma", OllamaHandler(model="gemma4:26b"))
    return registry


def main() -> None:
    settings = Settings()
    settings.apply_on_startup()          # propagates VAULT_*_PATH env vars

    cfg     = load_config()
    host_id = bytes.fromhex(cfg["host"]["id"])

    event_bus = EventBus()
    registry  = _build_handler_registry(settings)

    # Resource access
    slate_access = SlateAccess(host_id=host_id)
    vault_access = VaultAccess()

    # Engines
    parse_engine         = StrokeParseEngine()
    render_engine        = RenderEngine()
    vision_engine        = VisionEngine()
    validation_engine    = ValidationEngine()
    transcription_engine = TranscriptionEngine(registry=registry)
    diagram_engine       = DiagramEngine(registry=registry)

    # Managers
    ingest_manager = IngestManager(
        vision_engine        = vision_engine,
        validation_engine    = validation_engine,
        transcription_engine = transcription_engine,
        diagram_engine       = diagram_engine,
        vault_access         = vault_access,
        event_bus            = event_bus,
    )
    sync_manager = SyncManager(
        slate_access   = slate_access,
        parse_engine   = parse_engine,
        render_engine  = render_engine,
        ingest_manager = ingest_manager,
        event_bus      = event_bus,
    )

    # Client
    StatusBarClient(
        sync_manager = sync_manager,
        event_bus    = event_bus,
        settings     = settings,
        registry     = registry,
        slate_access = slate_access,
    ).run()


if __name__ == "__main__":
    main()
