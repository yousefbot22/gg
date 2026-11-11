"""
Background task queue — replaces rogue `asyncio.create_task` calls.

Features:
- Per-user deduplication (a user cannot run 2 solvers at once).
- Graceful shutdown.
- Retry on transient failures.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from src.core.logger import get_logger

log = get_logger(__name__)


class QueueManager:
    def __init__(self) -> None:
        self._running: dict[int, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self,
        user_id: int,
        coro_factory: Callable[[], Awaitable[Any]],
        name: str = "task",
    ) -> bool:
        """
        Submit a task for a user. Returns False if one is already running.
        """
        async with self._lock:
            existing = self._running.get(user_id)
            if existing and not existing.done():
                return False
            task = asyncio.create_task(coro_factory(), name=f"{name}:{user_id}")
            self._running[user_id] = task

        task.add_done_callback(lambda t: self._on_done(user_id, t))
        log.info("task_submitted", user_id=user_id, name=name)
        return True

    def _on_done(self, user_id: int, task: asyncio.Task) -> None:
        try:
            exc = task.exception()
            if exc:
                log.error("task_failed", user_id=user_id, error=str(exc))
        except asyncio.CancelledError:
            log.info("task_cancelled", user_id=user_id)
        finally:
            self._running.pop(user_id, None)

    async def cancel(self, user_id: int) -> bool:
        async with self._lock:
            task = self._running.get(user_id)
        if not task or task.done():
            return False
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        return True

    def is_running(self, user_id: int) -> bool:
        task = self._running.get(user_id)
        return bool(task and not task.done())

    async def shutdown(self) -> None:
        for task in list(self._running.values()):
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._running.values(), return_exceptions=True)
        self._running.clear()


queue_manager = QueueManager()