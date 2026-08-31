"""
macOS status bar client.

Component Type: Client (UI / Initiation Volatility).
Entry point. Knows *what* the user wants. Calls SyncManager only.
Does not call Engines or ResourceAccess directly.
Bridges rumps (NSRunLoop, main thread) to the asyncio pipeline via AsyncBridge.
"""

from __future__ import annotations

import rumps

from app.business_logic.managers.sync_manager    import ISyncManager
from app.business_logic.managers.watcher_manager import IWatcherManager
from app.client.preferences_window           import PreferencesWindowController
from app.client.sync_window                  import SyncWindowController
from app.resource_access.slate_access        import ISlateAccess
from app.utilities.async_bridge               import AsyncBridge
from app.utilities.event_bus                  import (
    DeviceDetectedEvent,
    EventBus,
    NoteIngestedEvent,
    NoteIngestFailedEvent,
    StatusUpdateEvent,
    SyncCompletedEvent,
    SyncFailedEvent,
    SyncStartedEvent,
)
from app.utilities.handler_registry           import HandlerRegistry
from app.utilities.models                     import SyncStatus
from app.utilities.settings                  import Settings


# Status bar text for each pipeline state.
_ICONS: dict[SyncStatus, str] = {
    SyncStatus.IDLE:     "✏",
    SyncStatus.SCANNING: "⊙",
    SyncStatus.SYNCING:  "↓",
    SyncStatus.ERROR:    "✕",
}


# rumps registers a single process-wide notification handler, so it needs a
# module reference back to the running client.
_ACTIVE_CLIENT: "StatusBarClient | None" = None


@rumps.notifications
def _on_notification_clicked(info) -> None:
    """Called on the main thread when the user clicks one of our notifications."""
    if _ACTIVE_CLIENT is None:
        return
    try:
        action = dict(info or {}).get("action", "")
    except Exception:
        return
    if action == "open_sync":
        _ACTIVE_CLIENT.m_sync_window.show()


class StatusBarClient(rumps.App):
    """
    macOS menu bar application.

    Component Type: Client (UI / Initiation Volatility).
    Subscribes to pipeline events to update icon and last-status text.
    All pipeline work is initiated through ISyncManager via AsyncBridge.
    """

    def __init__(
        self,
        sync_manager: ISyncManager,
        event_bus:    EventBus,
        settings:     Settings,
        registry:     HandlerRegistry,
        slate_access: ISlateAccess,
        watcher:      IWatcherManager,
    ) -> None:
        if sync_manager is None:
            raise ValueError("sync_manager must not be None")
        if event_bus is None:
            raise ValueError("event_bus must not be None")
        if settings is None:
            raise ValueError("settings must not be None")
        if registry is None:
            raise ValueError("registry must not be None")
        if slate_access is None:
            raise ValueError("slate_access must not be None")
        if watcher is None:
            raise ValueError("watcher must not be None")

        super().__init__(
            name  = "BambooSlate",
            title = _ICONS[SyncStatus.IDLE],
        )
        self.m_sync_manager = sync_manager
        self.m_event_bus    = event_bus
        self.m_watcher      = watcher
        self.m_bridge       = AsyncBridge()
        self.m_last_note    = rumps.MenuItem("No notes yet", callback=None)
        self.m_prefs_controller = (
            PreferencesWindowController.alloc()
            .initWithSettings_registry_(settings, registry)
        )
        self.m_prefs_controller.setSlateAccess_bridge_(slate_access, self.m_bridge)
        self.m_sync_window = (
            SyncWindowController.alloc()
            .initWithSyncManager_bridge_(sync_manager, self.m_bridge)
        )

        self.menu = [
            rumps.MenuItem("Sync Now",    callback=self.on_sync_now),
            None,
            self.m_last_note,
            None,
            rumps.MenuItem("Preferences", callback=self.on_preferences),
            None,
        ]

        self._subscribe_events()

        global _ACTIVE_CLIENT
        _ACTIVE_CLIENT = self

        # The loop itself checks the "watch for device" preference each tick, so
        # it is always started and idles while the preference is off.
        self.m_bridge.run(self.m_watcher.run())

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------

    def on_sync_now(self, _) -> None:
        self.m_sync_window.show()

    def on_preferences(self, _) -> None:
        self.m_prefs_controller.show()

    # ------------------------------------------------------------------
    # Event handlers (called from asyncio thread via event bus)
    # ------------------------------------------------------------------

    def _subscribe_events(self) -> None:
        self.m_event_bus.subscribe(SyncStartedEvent,      self._on_sync_started)
        self.m_event_bus.subscribe(SyncCompletedEvent,    self._on_sync_completed)
        self.m_event_bus.subscribe(SyncFailedEvent,       self._on_sync_failed)
        self.m_event_bus.subscribe(NoteIngestedEvent,     self._on_note_ingested)
        self.m_event_bus.subscribe(NoteIngestFailedEvent, self._on_note_ingest_failed)
        self.m_event_bus.subscribe(StatusUpdateEvent,     self._on_status_update)
        self.m_event_bus.subscribe(DeviceDetectedEvent,   self._on_device_detected)

    def _on_sync_started(self, _event: SyncStartedEvent) -> None:
        self._set_status(SyncStatus.SCANNING, "Scanning...")

    def _on_sync_completed(self, event: SyncCompletedEvent) -> None:
        msg = f"{event.synced_count} note(s) synced"
        self._set_status(SyncStatus.IDLE, msg)
        rumps.notification(title="Bamboo Slate", subtitle="", message=msg)

    def _on_sync_failed(self, event: SyncFailedEvent) -> None:
        self._set_status(SyncStatus.ERROR, event.reason)

    def _on_note_ingested(self, event: NoteIngestedEvent) -> None:
        self.m_last_note.title = f"Last: {event.doc_type} → {event.vault_name}"

    def _on_note_ingest_failed(self, event: NoteIngestFailedEvent) -> None:
        self.m_last_note.title = f"Failed: {event.reason[:60]}"

    def _on_device_detected(self, event: DeviceDetectedEvent) -> None:
        self.m_last_note.title = f"{event.name} nearby — click to sync"
        rumps.notification(
            title    = "Bamboo Slate",
            subtitle = f"{event.name} is nearby",
            message  = "Click to review and import your notes.",
            data     = {"action": "open_sync"},
        )

    def _on_status_update(self, event: StatusUpdateEvent) -> None:
        status = SyncStatus.SYNCING if event.busy else SyncStatus.IDLE
        self.title = _ICONS[status]
        self.m_last_note.title = event.message

    # ------------------------------------------------------------------

    def _set_status(self, status: SyncStatus, tooltip: str) -> None:
        self.title = _ICONS[status]
        self.m_last_note.title = tooltip if status != SyncStatus.IDLE else self.m_last_note.title

