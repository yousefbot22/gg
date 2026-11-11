"""Repository for saved_answers table."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from src.db.connection import get_conn, fetch_one, fetch_all
from src.db.models import SavedAnswer
from src.core.logger import get_logger

log = get_logger(__name__)


_ARABIC_DIACRITICS = re.compile(r"[\u064B-\u0652\u0670]")
_ALEF_FORMS = re.compile(r"[إأآٱ]")
_YAA_FORMS = re.compile(r"[ى]")
_TAA_MARBUTA = re.compile(r"[ة]")
_PUNCT = re.compile(r"[^\w\s]")


def normalize_arabic(text: str) -> str:
    """Normalize Arabic text for fuzzy comparison."""
    if not text:
        return ""
    t = str(text).replace("&#34;", '"').replace("&quot;", '"').replace("'", "")
    t = _ARABIC_DIACRITICS.sub("", t)
    t = _ALEF_FORMS.sub("ا", t)
    t = _YAA_FORMS.sub("ي", t)
    t = _TAA_MARBUTA.sub("ه", t)
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split()).strip().lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_answer(question_id: int) -> SavedAnswer | None:
    row = fetch_one(
        "SELECT * FROM saved_answers WHERE question_id = ?", (question_id,)
    )
    if not row:
        return None
    return SavedAnswer(**{k: row[k] for k in SavedAnswer.__dataclass_fields__})


def save_choice_answer(
    question_id: int,
    chapter_id: int,
    correct_choice_id: int,
    correct_content: str = "",
    explanation: str = "",
    question_text: str = "",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO saved_answers (
                question_id, chapter_id, question_type, correct_choice_id,
                correct_content, explanation, question_text, success_count, updated_at
            ) VALUES (?, ?, 'choice', ?, ?, ?, ?, 1, ?)
            ON CONFLICT(question_id) DO UPDATE SET
                correct_choice_id = excluded.correct_choice_id,
                correct_content = excluded.correct_content,
                explanation = excluded.explanation,
                success_count = saved_answers.success_count + 1,
                confidence = MIN(saved_answers.confidence + 0.05, 1.0),
                updated_at = excluded.updated_at
            """,
            (question_id, chapter_id, correct_choice_id, correct_content, explanation, question_text, _now()),
        )
        conn.commit()


def save_description_answer(
    question_id: int,
    chapter_id: int,
    model_answer: str,
    explanation: str = "",
    question_text: str = "",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO saved_answers (
                question_id, chapter_id, question_type, model_answer,
                explanation, question_text, success_count, updated_at
            ) VALUES (?, ?, 'description', ?, ?, ?, 1, ?)
            ON CONFLICT(question_id) DO UPDATE SET
                model_answer = excluded.model_answer,
                explanation = excluded.explanation,
                success_count = saved_answers.success_count + 1,
                updated_at = excluded.updated_at
            """,
            (question_id, chapter_id, model_answer, explanation, question_text, _now()),
        )
        conn.commit()


def count_total() -> int:
    row = fetch_one("SELECT COUNT(*) as c FROM saved_answers")
    return int(row["c"]) if row else 0


def get_chapter_answers(chapter_id: int) -> list[SavedAnswer]:
    rows = fetch_all(
        "SELECT * FROM saved_answers WHERE chapter_id = ? ORDER BY question_id",
        (chapter_id,),
    )
    return [
        SavedAnswer(**{k: r[k] for k in SavedAnswer.__dataclass_fields__ if k in r})
        for r in rows
    ]