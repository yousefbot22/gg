"""Repository for bot_users."""
from __future__ import annotations

from datetime import datetime, timezone

from src.db.connection import get_conn, fetch_one
from src.db.models import BotUser


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_profile(
    user_id: int,
    grade: str | None = None,
    subject: str | None = None,
    active_course_url: str | None = None,
) -> None:
    """Upsert user preferences. NEVER stores credentials."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO bot_users (user_id, grade, subject, active_course_url, created_at, updated_at)
            VALUES (?, COALESCE(?, 'grade_1'), COALESCE(?, 'programming'), ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                grade = COALESCE(excluded.grade, bot_users.grade),
                subject = COALESCE(excluded.subject, bot_users.subject),
                active_course_url = COALESCE(excluded.active_course_url, bot_users.active_course_url),
                updated_at = excluded.updated_at
            """,
            (user_id, grade, subject, active_course_url, _now(), _now()),
        )
        conn.commit()


def get(user_id: int) -> BotUser | None:
    r = fetch_one("SELECT * FROM bot_users WHERE user_id = ?", (user_id,))
    if not r:
        return None
    return BotUser(
        user_id=r["user_id"],
        grade=r["grade"],
        subject=r["subject"],
        active_course_url=r["active_course_url"],
        is_admin=bool(r["is_admin"]),
    )


def get_trial_count(user_id: int) -> int:
    r = fetch_one("SELECT solved_count FROM free_trial WHERE user_id = ?", (user_id,))
    return int(r["solved_count"]) if r else 0


def increment_trial(user_id: int, chapter_seq: int) -> int:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO free_trial (user_id, solved_count, last_chapter_seq, updated_at)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                solved_count = free_trial.solved_count + 1,
                last_chapter_seq = excluded.last_chapter_seq,
                updated_at = excluded.updated_at
            """,
            (user_id, chapter_seq, _now()),
        )
        conn.commit()
    return get_trial_count(user_id)