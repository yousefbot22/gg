"""Pytest fixtures."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


# Must be set BEFORE any src import
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST_TOKEN_FOR_TESTS")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("HEADLESS", "true")
os.environ.setdefault("ENABLE_FIREBASE", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch) -> Path:
    """Use a fresh SQLite DB for each test that needs it."""
    db_path = tmp_path / "test.db"

    # Override the module-level DB_PATH
    from src.db import connection
    monkeypatch.setattr(connection, "DB_PATH", db_path)

    # Run migrations on the fresh DB
    from src.db.migrations import run_migrations
    run_migrations(db_path)

    return db_path