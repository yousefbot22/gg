"""
Versioned schema migrations — replaces `CREATE TABLE IF NOT EXISTS`.

Each migration is idempotent and recorded in `schema_migrations`.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from src.db.connection import get_conn
from src.core.logger import get_logger

log = get_logger(__name__)


MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "initial_schema",
        [
            """
            CREATE TABLE IF NOT EXISTS saved_answers (
                question_id INTEGER PRIMARY KEY,
                chapter_id INTEGER NOT NULL,
                question_type TEXT NOT NULL CHECK(question_type IN ('choice','description')),
                correct_choice_id INTEGER,
                correct_content TEXT,
                model_answer TEXT,
                explanation TEXT,
                question_text TEXT,
                confidence REAL DEFAULT 1.0,
                success_count INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_answers_chapter ON saved_answers(chapter_id)",
            "CREATE INDEX IF NOT EXISTS idx_answers_type ON saved_answers(question_type)",

            """
            CREATE TABLE IF NOT EXISTS saved_chapters (
                chapter_id INTEGER PRIMARY KEY,
                course_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                test_type TEXT NOT NULL DEFAULT 'review',
                question_count INTEGER DEFAULT 0,
                completed INTEGER DEFAULT 0,
                diamond INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_chapters_course ON saved_chapters(course_id)",
            "CREATE INDEX IF NOT EXISTS idx_chapters_completed ON saved_chapters(course_id, completed)",

            """
            CREATE TABLE IF NOT EXISTS bot_users (
                user_id INTEGER PRIMARY KEY,
                grade TEXT DEFAULT 'grade_1',
                subject TEXT DEFAULT 'programming',
                active_course_url TEXT,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,

            """
            CREATE TABLE IF NOT EXISTS subscription_groups (
                group_id TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                tier_name TEXT NOT NULL,
                max_users INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,

            """
            CREATE TABLE IF NOT EXISTS group_members (
                group_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                student_username TEXT,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (group_id, user_id),
                FOREIGN KEY (group_id) REFERENCES subscription_groups(group_id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_members_user ON group_members(user_id)",

            """
            CREATE TABLE IF NOT EXISTS completed_students (
                group_id TEXT NOT NULL,
                student_username TEXT NOT NULL,
                grade TEXT,
                completed_at TEXT NOT NULL,
                PRIMARY KEY (group_id, student_username),
                FOREIGN KEY (group_id) REFERENCES subscription_groups(group_id) ON DELETE CASCADE
            )
            """,

            """
            CREATE TABLE IF NOT EXISTS free_trial (
                user_id INTEGER PRIMARY KEY,
                solved_count INTEGER DEFAULT 0,
                last_chapter_seq INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """,

            """
            CREATE TABLE IF NOT EXISTS financial_literacy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question_text TEXT NOT NULL,
                question_hash TEXT NOT NULL,
                options_json TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                explanation TEXT,
                topic TEXT,
                source TEXT DEFAULT 'user_training',
                confidence REAL DEFAULT 1.0,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_fin_hash ON financial_literacy(question_hash)",

            """
            CREATE TABLE IF NOT EXISTS admin_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        ],
    ),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_migrations(db_path=None) -> None:
    """Apply all pending migrations."""
    with get_conn(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
        """)
        conn.commit()

        cur = conn.execute("SELECT version FROM schema_migrations")
        applied = {row["version"] for row in cur.fetchall()}

        for version, name, statements in MIGRATIONS:
            if version in applied:
                continue
            log.info("applying_migration", version=version, name=name)
            try:
                for stmt in statements:
                    conn.execute(stmt)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, _now_iso()),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                log.error("migration_failed", version=version, error=str(e))
                raise

    log.info("migrations_complete", total=len(MIGRATIONS))