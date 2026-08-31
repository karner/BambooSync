"""
Async event bus.

Component Type: Utility (Cross-cutting).
Provides publish/subscribe for pipeline events. Only Managers publish;
only the Client (and other Managers via queue) subscribe.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


# ---------------------------------------------------------------------------
# Event contracts
# ---------------------------------------------------------------------------

@dataclass
class PipelineEvent:
    """Base for all pipeline events."""


@dataclass
class SyncStartedEvent(PipelineEvent):
    pass


@dataclass
class SyncCompletedEvent(PipelineEvent):
    synced_count: int


@dataclass
class SyncFailedEvent(PipelineEvent):
    reason: str


@dataclass
class NoteDownloadedEvent(PipelineEvent):
    png_path: str
    timestamp: int


@dataclass
class NoteIngestedEvent(PipelineEvent):
    vault_name:  str
    doc_type:    str
    output_path: str


@dataclass
class NoteIngestFailedEvent(PipelineEvent):
    png_path: str
    reason:   str


@dataclass
class DeviceDetectedEvent(PipelineEvent):
    """The configured Slate has appeared on BLE. Announcement only — nothing
    has been read from the device."""
    address: str
    name:    str


@dataclass
class StatusUpdateEvent(PipelineEvent):
    """
    Carries a short human-readable status string for the menu bar.
    busy=False marks a terminal status: work has stopped, icon returns to idle.
    """
    message: str
    busy:    bool = True


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------

Handler = Callable[[PipelineEvent], Coroutine[Any, Any, None] | None]


class EventBus:
    """
    Simple in-process async pub/sub bus.

    Component Type: Utility (Cross-cutting).
    Subscribers register for specific event types. Publishers call publish()
    without knowing who is listening.
    """

    def __init__(self) -> None:
        self.m_handlers: dict[type, list[Handler]] = {}

    def subscribe(self, event_type: type, handler: Handler) -> None:
        if event_type not in self.m_handlers:
            self.m_handlers[event_type] = []
        self.m_handlers[event_type].append(handler)

    async def publish(self, event: PipelineEvent) -> None:
        for handler in self.m_handlers.get(type(event), []):
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
