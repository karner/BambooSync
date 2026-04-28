"""
BLE sync manager.

Component Type: Manager (Workflow Volatility).
Orchestrates the full device sync workflow: scan → connect → download
strokes → parse → render → queue to IngestManager → delete from device.
Knows *when* each step runs; does not implement any algorithm.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path

from app.business_logic.engines.render_engine      import IRenderEngine
from app.business_logic.engines.stroke_parse_engine import IStrokeParseEngine
from app.business_logic.managers.ingest_manager    import IIngestManager
from app.resource_access.slate_access              import ISlateAccess
from app.utilities.config                          import load_config
from app.utilities.event_bus                       import (
    EventBus,
    NoteDownloadedEvent,
    SyncCompletedEvent,
    SyncFailedEvent,
    SyncStartedEvent,
    StatusUpdateEvent,
)
from app.utilities.models                          import SyncResult


# Temporary PNG storage during one sync session; files are not kept after ingest.
_SCRATCH_DIR = Path(__file__).parent.parent.parent.parent / "_scratch"


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class ISyncManager(ABC):

    @abstractmethod
    async def sync_all(self) -> SyncResult:
        """
        Connects to the Slate, downloads all stored drawings, runs the ingest
        pipeline for each, and deletes them from the device on success.
        """

    @abstractmethod
    async def sync_once(self) -> SyncResult:
        """Downloads and processes exactly one drawing (oldest on device)."""


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class SyncManager(ISyncManager):
    """
    Orchestrates the Slate sync workflow.

    Component Type: Manager (Workflow Volatility).
    Encapsulates when to connect, how many drawings to process, and when
    to delete. Delegates WILL 2.0 parsing to StrokeParseEngine, rendering
    to RenderEngine, and queues each rendered PNG to IngestManager.
    Publishes SyncStartedEvent, NoteDownloadedEvent, SyncCompletedEvent,
    or SyncFailedEvent via the EventBus.
    """

    _SCAN_TIMEOUT = 30.0  # seconds to wait for device to appear on BLE

    def __init__(
        self,
        slate_access:   ISlateAccess,
        parse_engine:   IStrokeParseEngine,
        render_engine:  IRenderEngine,
        ingest_manager: IIngestManager,
        event_bus:      EventBus,
    ) -> None:
        if slate_access is None:
            raise ValueError("slate_access must not be None")
        if parse_engine is None:
            raise ValueError("parse_engine must not be None")
        if render_engine is None:
            raise ValueError("render_engine must not be None")
        if ingest_manager is None:
            raise ValueError("ingest_manager must not be None")
        if event_bus is None:
            raise ValueError("event_bus must not be None")

        self.m_slate_access   = slate_access
        self.m_parse_engine   = parse_engine
        self.m_render_engine  = render_engine
        self.m_ingest_manager = ingest_manager
        self.m_event_bus      = event_bus

        cfg = load_config()
        self.m_device_address = cfg["device"]["address"]

    async def sync_all(self) -> SyncResult:
        await self.m_event_bus.publish(SyncStartedEvent())
        await self.m_event_bus.publish(StatusUpdateEvent("Scanning for Slate..."))

        device = await self.m_slate_access.find_device(self.m_device_address, self._SCAN_TIMEOUT)
        if device is None:
            await self.m_event_bus.publish(SyncFailedEvent(reason="Device not found"))
            return SyncResult(synced_count=0, failed_count=0, errors=["Device not found"])

        synced = 0
        failed = 0
        errors: list[str] = []

        async with self.m_slate_access.connect(device) as session:
            count = await self.m_slate_access.file_count(session)
            await self.m_event_bus.publish(StatusUpdateEvent(f"Syncing {count} note(s)..."))

            while count > 0:
                try:
                    result = await self._sync_one(session, synced + 1, count)
                    if result:
                        synced += 1
                    else:
                        failed += 1
                except Exception as exc:
                    failed += 1
                    errors.append(str(exc))
                count -= 1

        await self.m_event_bus.publish(SyncCompletedEvent(synced_count=synced))
        return SyncResult(synced_count=synced, failed_count=failed, errors=errors)

    async def sync_once(self) -> SyncResult:
        await self.m_event_bus.publish(SyncStartedEvent())

        device = await self.m_slate_access.find_device(self.m_device_address, self._SCAN_TIMEOUT)
        if device is None:
            await self.m_event_bus.publish(SyncFailedEvent(reason="Device not found"))
            return SyncResult(synced_count=0, failed_count=1, errors=["Device not found"])

        async with self.m_slate_access.connect(device) as session:
            success = await self._sync_one(session, 1, 1)

        count = 1 if success else 0
        await self.m_event_bus.publish(SyncCompletedEvent(synced_count=count))
        return SyncResult(synced_count=count, failed_count=0 if success else 1)

    # ------------------------------------------------------------------

    async def _sync_one(self, session, index: int, total: int) -> bool:
        """Downloads, parses, renders, ingests, and deletes one drawing. Returns success."""
        _SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

        _, ts   = await self.m_slate_access.stroke_metadata(session)
        label   = time.strftime("%Y%m%d_%H%M%S", time.gmtime(ts))
        png_path = _SCRATCH_DIR / f"{label}.png"

        raw     = await self.m_slate_access.download_oldest(session)
        strokes = self.m_parse_engine.parse(raw)
        drawn   = self.m_render_engine.render(strokes, png_path)

        if not drawn:
            await self.m_slate_access.delete_oldest(session)
            return True  # empty drawing; treated as success

        await self.m_event_bus.publish(NoteDownloadedEvent(png_path=str(png_path), timestamp=ts))

        # Queue to IngestManager (one Manager → one other Manager per use case).
        await self.m_ingest_manager.process_note(png_path, ts)

        await self.m_slate_access.delete_oldest(session)
        return True
