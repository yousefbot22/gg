"""
Database package — auto-runs migrations on import.

⚠️ IMPORTANT: This module MUST be import-safe (no side effects that
could crash the bot during import). Migrations are quick (<50ms)
and idempotent, so running them at import time is acceptable.
"""
from src.db.migrations import run_migrations
from src.db.repositories.chapters_repo import seed_defaults

# Run migrations once at package import
run_migrations()
seed_defaults()