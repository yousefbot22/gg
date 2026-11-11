"""
Thread-safe SQLite connection management with WAL mode.

- Uses `aiosqlite` semantics via `asyncio.to_thread` for non-blocking access.
- WAL mode for concurrent reads.
- Connection-per-task pattern (SQLite is not multi-writer).
"""
from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import AsyncIterator, Iterator

from src.config import settings
from src.core.logger import get_logger

log = get_logger(__name__)

DB_PATH: Path = settings.data_dir / "answers.db"


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Create a new configured connection."""
    conn = sqlite3.connect(
        str(db_path or DB_PATH),
        timeout=30.0,
        isolation_level=None,  # autocommit; we manage transactions manually
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Synchronous context manager for a connection."""
    conn = _connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def async_conn(db_path: Path | None = None) -> AsyncIterator[sqlite3.Connection]:
    """Async wrapper — runs in thread pool."""
    conn = await asyncio.to_thread(_connect, db_path)
    try:
        yield conn
    finally:
        await asyncio.to_thread(conn.close)


def execute_sync(query: str, params: tuple = (), db_path: Path | None = None) -> None:
    """Fire-and-forget write (sync)."""
    with get_conn(db_path) as conn:
        conn.execute(query, params)
        conn.commit()


async def execute(query: str, params: tuple = (), db_path: Path | None = None) -> None:
    """Async fire-and-forget write."""
    def _run():
        with get_conn(db_path) as conn:
            conn.execute(query, params)
            conn.commit()
    await asyncio.to_thread(_run)


def fetch_one(query: str, params: tuple = (), db_path: Path | None = None) -> dict | None:
    with get_conn(db_path) as conn:
        cur = conn.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_all(query: str, params: tuple = (), db_path: Path | None = None) -> list[dict]:
    with get_conn(db_path) as conn:
        cur = conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]