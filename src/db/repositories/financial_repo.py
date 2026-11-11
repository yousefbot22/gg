"""Repository for financial literacy bank."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from src.db.connection import get_conn, fetch_one, fetch_all
from src.db.models import FinancialQuestion
from src.db.repositories.answers_repo import normalize_arabic


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(text: str) -> str:
    return hashlib.sha256(normalize_arabic(text).encode("utf-8")).hexdigest()


def save(
    question_text: str,
    options: list[str],
    correct_answer: str,
    explanation: str = "",
    topic: str = "",
    user_id: int | None = None,
    source: str = "user_training",
) -> int:
    qh = _hash(question_text)
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO financial_literacy (
                user_id, question_text, question_hash, options_json,
                correct_answer, explanation, topic, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(question_hash) DO UPDATE SET
                correct_answer = excluded.correct_answer,
                explanation = excluded.explanation,
                confidence = MIN(financial_literacy.confidence + 0.1, 1.0)
            """,
            (user_id, question_text, qh, json.dumps(options, ensure_ascii=False),
             correct_answer, explanation, topic, source, _now()),
        )
        conn.commit()
        return cur.lastrowid or 0


def find(question_text: str) -> FinancialQuestion | None:
    """Exact hash match, then fuzzy fallback."""
    qh = _hash(question_text)
    r = fetch_one("SELECT * FROM financial_literacy WHERE question_hash = ?", (qh,))
    if r:
        return _row_to_model(r)

    # Fuzzy match
    target = normalize_arabic(question_text)
    rows = fetch_all("SELECT * FROM financial_literacy")
    best, best_score = None, 0.0
    for row in rows:
        norm = normalize_arabic(row["question_text"])
        if norm == target:
            return _row_to_model(row)
        # word overlap
        t_words = set(target.split())
        n_words = set(norm.split())
        if t_words and n_words:
            score = len(t_words & n_words) / len(t_words | n_words)
            if score > best_score and score > 0.6:
                best_score = score
                best = row
    return _row_to_model(best) if best else None


def _row_to_model(r: dict) -> FinancialQuestion:
    try:
        options = json.loads(r["options_json"]) if r["options_json"] else []
    except Exception:
        options = []
    return FinancialQuestion(
        id=r["id"],
        question_text=r["question_text"],
        question_hash=r["question_hash"],
        options=options,
        correct_answer=r["correct_answer"],
        explanation=r["explanation"] or "",
        topic=r["topic"] or "",
        user_id=r["user_id"],
        source=r["source"],
        confidence=r["confidence"],
    )


def count() -> int:
    r = fetch_one("SELECT COUNT(*) as c FROM financial_literacy")
    return int(r["c"]) if r else 0