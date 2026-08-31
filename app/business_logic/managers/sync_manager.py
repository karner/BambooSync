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
from app.utilities.event_bus                       import (
    EventBus,
    NoteDownloadedEvent,
    SyncCompletedEvent,
    SyncFailedEvent,
    SyncStartedEvent,
    StatusUpdateEvent,
)
from app.utilities.logger                          import get_logger
from app.utilities.models                          import NotePreview, SyncResult
from app.utilities.settings                        import Settings

_log = get_logger(__name__)


# Fallback working directory, used when Preferences names no scratch directory.
_DEFAULT_SCRATCH_DIR = Path(__file__).parent.parent.parent.parent / "_scratch"


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

    @abstractmethod
    async def list_notes(self) -> list[NotePreview]:
        """
        Connects to the Slate and downloads all stored drawings.
        Each note is deleted from the device as part of iteration (protocol requirement —
        delete_oldest is the only way to advance the file pointer), so the raw bytes are
        spooled to disk first and stay there until import succeeds.
        Returns NotePreview objects; does NOT run the ingest pipeline.
        Raises RuntimeError when the device cannot be found.
        """

    @abstractmethod
    async def import_notes(self, previews: list[NotePreview]) -> SyncResult:
        """Runs parse→render→ingest for the given in-memory NotePreview objects."""


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

    def __init__(
        self,
        slate_access:   ISlateAccess,
        parse_engine:   IStrokeParseEngine,
        render_engine:  IRenderEngine,
        ingest_manager: IIngestManager,
        event_bus:      EventBus,
        settings:       Settings,
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
        if settings is None:
            raise ValueError("settings must not be None")

        self.m_slate_access   = slate_access
        self.m_parse_engine   = parse_engine
        self.m_render_engine  = render_engine
        self.m_ingest_manager = ingest_manager
        self.m_event_bus      = event_bus
        self.m_settings       = settings

    async def sync_all(self) -> SyncResult:
        await self.m_event_bus.publish(SyncStartedEvent())
        await self.m_event_bus.publish(StatusUpdateEvent("Scanning for Slate..."))

        device, reason = await self._find_device()
        if device is None:
            await self.m_event_bus.publish(SyncFailedEvent(reason=reason))
            return SyncResult(synced_count=0, failed_count=0, errors=[reason])

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

        device, reason = await self._find_device()
        if device is None:
            await self.m_event_bus.publish(SyncFailedEvent(reason=reason))
            return SyncResult(synced_count=0, failed_count=1, errors=[reason])

        async with self.m_slate_access.connect(device) as session:
            success = await self._sync_one(session, 1, 1)

        count = 1 if success else 0
        await self.m_event_bus.publish(SyncCompletedEvent(synced_count=count))
        return SyncResult(synced_count=count, failed_count=0 if success else 1)

    async def list_notes(self) -> list[NotePreview]:
        await self.m_event_bus.publish(StatusUpdateEvent("Connecting to Slate…"))

        device, reason = await self._find_device()
        if device is None:
            await self.m_event_bus.publish(SyncFailedEvent(reason=reason))
            raise RuntimeError(reason)

        spool_dir = self._spool_dir()

        previews: list[NotePreview] = []
        async with self.m_slate_access.connect(device) as session:
            count = await self.m_slate_access.file_count(session)
            for i in range(count):
                await self.m_event_bus.publish(
                    StatusUpdateEvent(f"Fetching note {i + 1}/{count}…")
                )
                stroke_bytes, ts = await self.m_slate_access.stroke_metadata(session)
                raw              = await self.m_slate_access.download_oldest(session)

                # Spool before deleting: delete_oldest is irreversible and is the
                # only way to reach the next note.
                raw_path = spool_dir / f"{self._label(ts)}_{i:03d}.bin"
                raw_path.write_bytes(raw)

                await self.m_slate_access.delete_oldest(session)
                previews.append(NotePreview(
                    index             = i,
                    timestamp         = ts,
                    stroke_byte_count = stroke_bytes,
                    raw_bytes         = raw,
                    raw_path          = raw_path,
                ))

        message = (
            f"{len(previews)} note(s) ready to import"
            if previews else "No notes stored on device"
        )
        await self.m_event_bus.publish(StatusUpdateEvent(message, busy=False))
        return previews

    async def import_notes(self, previews: list[NotePreview]) -> SyncResult:
        await self.m_event_bus.publish(SyncStartedEvent())
        scratch_dir = self._scratch_dir()

        synced = 0
        failed = 0
        errors: list[str] = []

        for i, preview in enumerate(previews):
            await self.m_event_bus.publish(
                StatusUpdateEvent(f"Importing note {i + 1}/{len(previews)}…")
            )
            try:
                png_path = scratch_dir / f"{self._label(preview.timestamp)}.png"
                strokes  = self.m_parse_engine.parse(preview.raw_bytes)
                drawn    = self.m_render_engine.render(strokes, png_path)
                if drawn:
                    await self.m_event_bus.publish(
                        NoteDownloadedEvent(png_path=str(png_path), timestamp=preview.timestamp)
                    )
                    await self.m_ingest_manager.process_note(png_path, preview.timestamp)
                synced += 1
                self._discard_spool(preview)      # ingested; raw copy no longer needed
            except Exception as exc:
                failed += 1
                errors.append(str(exc))           # spool file is kept for retry

        result = SyncResult(synced_count=synced, failed_count=failed, errors=errors)
        await self.m_event_bus.publish(SyncCompletedEvent(synced_count=synced))
        return result

    # ------------------------------------------------------------------

    def _scratch_dir(self) -> Path:
        """
        Working directory for temporary PNGs. Read from Preferences per use so a
        change takes effect without restarting, and falls back to the project
        _scratch/ when unset or when the configured path cannot be created.
        """
        configured = self.m_settings.get_scratch_dir().strip()
        if configured:
            base = Path(configured).expanduser()
            try:
                base.mkdir(parents=True, exist_ok=True)
                return base
            except OSError as exc:
                _log.warning(
                    "Scratch directory %s unusable (%s) — falling back to %s",
                    base, exc, _DEFAULT_SCRATCH_DIR,
                )
        _DEFAULT_SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        return _DEFAULT_SCRATCH_DIR

    def _spool_dir(self) -> Path:
        """Raw WILL bytes live here from download until the note is ingested."""
        spool = self._scratch_dir() / "spool"
        spool.mkdir(parents=True, exist_ok=True)
        return spool

    async def _find_device(self):
        """
        Resolves the configured device from Settings and scans for it.

        Read on every sync rather than cached at construction, so a device
        picked in Preferences takes effect without restarting the app.
        Returns (device, reason); device is None when no device is configured
        or the scan found nothing, and reason says which.
        """
        address = self.m_settings.get_device_address().strip()
        if not address:
            return None, "No device selected — choose one in Preferences ▸ Device."

        timeout = self.m_settings.get_device_scan_timeout()
        device  = await self.m_slate_access.find_device(address, timeout)
        if device is None:
            return None, (
                f"Bamboo Slate not found at {address} — "
                f"switch the device on and try again."
            )
        return device, ""

    @staticmethod
    def _label(timestamp: int) -> str:
        return time.strftime("%Y%m%d_%H%M%S", time.gmtime(timestamp))

    @staticmethod
    def _discard_spool(preview: NotePreview) -> None:
        """Removes the spooled raw copy once the note is safely ingested."""
        if preview.raw_path is not None:
            preview.raw_path.unlink(missing_ok=True)

    async def _sync_one(self, session, index: int, total: int) -> bool:
        """Downloads, parses, renders, ingests, and deletes one drawing. Returns success."""
        scratch_dir = self._scratch_dir()

        _, ts   = await self.m_slate_access.stroke_metadata(session)
        png_path = scratch_dir / f"{self._label(ts)}.png"

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
