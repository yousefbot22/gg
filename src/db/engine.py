"""DB engine — SQLite connection context manager."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.config import Config

_DB_PATH = Path(getattr(Config, "DB_PATH", "data/bot.db"))
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection():
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()