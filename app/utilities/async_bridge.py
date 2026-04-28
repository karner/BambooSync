"""
Asyncio / NSRunLoop bridge.

Component Type: Utility (Cross-cutting).
Runs an asyncio event loop in a background daemon thread so that
rumps (which owns the main-thread NSRunLoop) can schedule coroutines
without blocking the status bar UI.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Coroutine


class AsyncBridge:
    """
    Starts a background asyncio loop on construction.

    Usage:
        bridge = AsyncBridge()
        future = bridge.run(some_coroutine())
        future.add_done_callback(lambda f: ...)
    """

    def __init__(self) -> None:
        self.m_loop = asyncio.new_event_loop()
        t = threading.Thread(target=self.m_loop.run_forever, daemon=True, name="asyncio-bridge")
        t.start()

    def run(self, coro: Coroutine[Any, Any, Any]) -> Future:
        """Schedules coro on the background loop. Returns a concurrent.futures.Future."""
        return asyncio.run_coroutine_threadsafe(coro, self.m_loop)

    def stop(self) -> None:
        self.m_loop.call_soon_threadsafe(self.m_loop.stop)
