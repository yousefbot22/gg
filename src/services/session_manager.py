"""
Thread-safe per-user session management.

Replaces the old module-level `user_sessions: dict` which was a race condition
disaster under concurrency.

Features:
- One asyncio.Lock per user (no global lock contention).
- Auto-cleanup of stale sessions (LRU-ish with max size).
- Encapsulated state — handlers never touch raw dicts.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from src.core.logger import get_logger
from src.solver.qureo_client import QureoClient
from src.solver.spx_client import SPXClient

log = get_logger(__name__)

MAX_SESSIONS = 500
SESSION_TTL_SEC = 3600 * 6  # 6 hours idle


@dataclass
class UserSession:
    user_id: int
    grade: str = "grade_1"
    course_url: str = ""
    username: str | None = None
    password: str | None = None
    is_logged_in: bool = False
    is_admin: bool = False
    is_solving: bool = False
    active_group_id: str | None = None
    active_platform: str = "qureo"  # or "spx"
    tracked_messages: set[int] = field(default_factory=set)
    qureo_client: QureoClient | None = None
    spx_client: SPXClient | None = None
    active_task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_seen: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    async def cleanup(self) -> None:
        """Close any open clients."""
        if self.active_task and not self.active_task.done():
            self.active_task.cancel()
            try:
                await self.active_task
            except (asyncio.CancelledError, Exception):
                pass
        for client in (self.qureo_client, self.spx_client):
            if client is not None:
                try:
                    await client.stop()
                except Exception as e:
                    log.warning("client_cleanup_failed", error=str(e))
        self.qureo_client = None
        self.spx_client = None
        self.active_task = None
        self.is_solving = False
        self.is_logged_in = False
        self.username = None
        self.password = None


class SessionManager:
    """Global session registry."""

    def __init__(self) -> None:
        self._sessions: dict[int, UserSession] = {}
        self._locks: dict[int, asyncio.Lock] = {}  # per-user create-lock
        self._global = asyncio.Lock()

    async def get(self, user_id: int) -> UserSession:
        """Get or create a session — always thread-safe."""
        if user_id in self._sessions:
            session = self._sessions[user_id]
            session.touch()
            return session

        async with self._global:
            # Double-check after acquiring lock
            if user_id in self._sessions:
                return self._sessions[user_id]
            if len(self._sessions) >= MAX_SESSIONS:
                await self._evict_oldest()
            session = UserSession(user_id=user_id)
            self._sessions[user_id] = session
            log.debug("session_created", user_id=user_id, total=len(self._sessions))
            return session

    async def remove(self, user_id: int) -> None:
        async with self._global:
            session = self._sessions.pop(user_id, None)
        if session:
            await session.cleanup()
            log.info("session_removed", user_id=user_id)

    async def _evict_oldest(self) -> None:
        if not self._sessions:
            return
        oldest_id = min(self._sessions, key=lambda k: self._sessions[k].last_seen)
        await self.remove(oldest_id)

    async def cleanup_idle(self) -> int:
        """Called periodically from main loop."""
        now = time.monotonic()
        stale = [
            uid for uid, s in self._sessions.items()
            if now - s.last_seen > SESSION_TTL_SEC and not s.is_solving
        ]
        for uid in stale:
            await self.remove(uid)
        if stale:
            log.info("sessions_evicted", count=len(stale))
        return len(stale)

    async def close_all(self) -> None:
        for uid in list(self._sessions):
            await self.remove(uid)

    def stats(self) -> dict[str, Any]:
        return {
            "active": len(self._sessions),
            "max": MAX_SESSIONS,
            "solving": sum(1 for s in self._sessions.values() if s.is_solving),
        }


session_manager = SessionManager()