"""
Device watcher.

Component Type: Manager (Workflow Volatility).
Polls BLE for the configured Slate and announces when it appears. Deliberately
does not touch the device: downloading is destructive (delete_oldest is the only
way to advance the file pointer), so it stays a user-initiated action through the
review window. The watcher only answers "is it here?".
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from app.resource_access.slate_access import ISlateAccess
from app.utilities.event_bus          import (
    DeviceDetectedEvent,
    EventBus,
    StatusUpdateEvent,
    SyncCompletedEvent,
    SyncFailedEvent,
    SyncStartedEvent,
)
from app.utilities.logger             import get_logger
from app.utilities.settings           import Settings

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class IWatcherManager(ABC):

    @abstractmethod
    async def run(self) -> None:
        """
        Long-running poll loop. Publishes DeviceDetectedEvent each time the
        configured Slate goes from absent to present. Returns when stop() is called.
        """

    @abstractmethod
    def stop(self) -> None:
        """Asks the loop to exit. Safe to call from another thread."""


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class WatcherManager(IWatcherManager):
    """
    Watches for the configured Slate appearing on BLE.

    Component Type: Manager (Workflow Volatility).
    Reads Settings on every tick, so enabling the watcher or switching device
    takes effect without restarting the app. Announces the edge only: a device
    left switched on is reported once, not on every poll.
    """

    _POLL_INTERVAL = 30.0   # seconds between scans
    _SCAN_TIMEOUT  = 8.0    # seconds each scan waits for the device
    _SLEEP_STEP    = 1.0    # granularity of the wait, so stop() is responsive

    def __init__(
        self,
        slate_access: ISlateAccess,
        event_bus:    EventBus,
        settings:     Settings,
    ) -> None:
        if slate_access is None:
            raise ValueError("slate_access must not be None")
        if event_bus is None:
            raise ValueError("event_bus must not be None")
        if settings is None:
            raise ValueError("settings must not be None")

        self.m_slate_access = slate_access
        self.m_event_bus    = event_bus
        self.m_settings     = settings

        self.m_running = False
        self.m_present = False   # was the device visible on the previous tick?
        self.m_busy    = False   # a sync holds the radio; don't scan over it

        event_bus.subscribe(SyncStartedEvent,   self._on_busy)
        event_bus.subscribe(StatusUpdateEvent,  self._on_status)
        event_bus.subscribe(SyncCompletedEvent, self._on_idle)
        event_bus.subscribe(SyncFailedEvent,    self._on_idle)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        self.m_running = True
        _log.info("Watcher started")
        while self.m_running:
            try:
                await self._tick()
            except Exception as exc:
                # A BLE hiccup must not end the watch; try again next interval.
                _log.warning("Watcher tick failed: %s", exc)
                self.m_present = False
            await self._sleep(self._POLL_INTERVAL)
        _log.info("Watcher stopped")

    def stop(self) -> None:
        self.m_running = False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _tick(self) -> None:
        if self.m_busy or not self.m_settings.get_auto_sync():
            return

        address = self.m_settings.get_device_address().strip()
        if not address:
            return

        device = await self.m_slate_access.find_device(address, self._SCAN_TIMEOUT)
        if device is None:
            self.m_present = False   # next appearance is a fresh edge
            return
        if self.m_present:
            return                   # already announced this appearance

        self.m_present = True
        name = (
            self.m_settings.get_device_name()
            or getattr(device, "name", "")
            or "Bamboo Slate"
        )
        _log.info("Slate detected at %s", address)
        await self.m_event_bus.publish(DeviceDetectedEvent(address=address, name=name))

    async def _sleep(self, seconds: float) -> None:
        """Sleeps in steps so stop() does not wait out a whole interval."""
        remaining = seconds
        while remaining > 0 and self.m_running:
            await asyncio.sleep(min(self._SLEEP_STEP, remaining))
            remaining -= self._SLEEP_STEP

    # -- busy tracking -------------------------------------------------

    def _on_busy(self, _event) -> None:
        self.m_busy = True

    def _on_idle(self, _event) -> None:
        self.m_busy = False
        # A sync just cleared the device; require it to disappear and return
        # before announcing again.
        self.m_present = True

    def _on_status(self, event: StatusUpdateEvent) -> None:
        self.m_busy = event.busy
