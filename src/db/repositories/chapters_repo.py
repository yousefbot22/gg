"""Repository for saved_chapters."""
from __future__ import annotations

from datetime import datetime, timezone

from src.db.connection import get_conn, fetch_one, fetch_all
from src.db.models import SavedChapter
from src.core.logger import get_logger

log = get_logger(__name__)


DEFAULT_PYTHON_CHAPTERS: list[dict] = [
    {"id": 511001, "seq": 1, "name": "مقدمة", "test_type": "review", "question_count": 6},
    {"id": 511002, "seq": 2, "name": "الحسابات والنصوص", "test_type": "review", "question_count": 9},
    {"id": 511003, "seq": 3, "name": "المتغيرات", "test_type": "review", "question_count": 6},
    {"id": 511004, "seq": 4, "name": "مراجعة الفهم 1", "test_type": "test", "question_count": 8},
    {"id": 511005, "seq": 5, "name": "جملة if", "test_type": "review", "question_count": 5},
    {"id": 511006, "seq": 6, "name": "جمل if - else", "test_type": "review", "question_count": 5},
    {"id": 511007, "seq": 7, "name": "جمل elif", "test_type": "review", "question_count": 5},
    {"id": 511008, "seq": 8, "name": "مراجعة الفهم 2", "test_type": "test", "question_count": 7},
    {"id": 511009, "seq": 9, "name": "العامل المنطقي", "test_type": "review", "question_count": 5},
    {"id": 511010, "seq": 10, "name": "العملية التكرارية", "test_type": "review", "question_count": 5},
    {"id": 511011, "seq": 11, "name": "مراجعة الفهم 3", "test_type": "test", "question_count": 6},
    {"id": 511012, "seq": 12, "name": "الدالة (1)", "test_type": "review", "question_count": 5},
    {"id": 511013, "seq": 13, "name": "الدالة (2)", "test_type": "review", "question_count": 5},
    {"id": 511014, "seq": 14, "name": "مراجعة الفهم 4", "test_type": "test", "question_count": 6},
    {"id": 511015, "seq": 15, "name": "المصفوفة (1)", "test_type": "review", "question_count": 5},
    {"id": 511016, "seq": 16, "name": "المصفوفة (2)", "test_type": "review", "question_count": 5},
    {"id": 511017, "seq": 17, "name": "مراجعة الفهم 5", "test_type": "test", "question_count": 6},
    {"id": 511018, "seq": 18, "name": "bool", "test_type": "review", "question_count": 5},
    {"id": 511019, "seq": 19, "name": "الدوال (3)", "test_type": "review", "question_count": 5},
    {"id": 511020, "seq": 20, "name": "مراجعة الفهم 6", "test_type": "test", "question_count": 6},
    {"id": 511021, "seq": 21, "name": "مراجعة الفهم 7", "test_type": "test", "question_count": 6},
    {"id": 511022, "seq": 22, "name": "مراجعة الفهم 8", "test_type": "test", "question_count": 6},
    {"id": 511023, "seq": 23, "name": "جملة for والمصفوفة", "test_type": "review", "question_count": 5},
    {"id": 511024, "seq": 24, "name": "مراجعة الفهم 9", "test_type": "test", "question_count": 6},
    {"id": 511025, "seq": 25, "name": "مراجعة الفهم 10", "test_type": "test", "question_count": 6},
]


def _default_js_chapters() -> list[dict]:
    return [
        {
            "id": 90000 + i,
            "seq": i,
            "name": (
                "المخطط الانسيابي" if i == 32
                else "مراجعة المتغيرات والعمليات" if i == 31
                else "مراجعة الفهم" if (i % 4 == 0 or i == 33)
                else f"الفصل {i}"
            ),
            "test_type": "test" if (i % 4 == 0 or i == 33) else "review",
            "question_count": 5,
        }
        for i in range(1, 41)
    ]


DEFAULT_JS_CHAPTERS = _default_js_chapters()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_defaults() -> None:
    """Seed default chapters for both courses."""
    _save_batch(DEFAULT_PYTHON_CHAPTERS, "python_short_ar")
    _save_batch(DEFAULT_JS_CHAPTERS, "javascript_ar")


def _save_batch(chapters: list[dict], course_id: str) -> None:
    with get_conn() as conn:
        for c in chapters:
            conn.execute(
                """
                INSERT INTO saved_chapters (
                    chapter_id, course_id, seq, name, url, test_type,
                    question_count, completed, diamond, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
                ON CONFLICT(chapter_id) DO UPDATE SET
                    name = CASE WHEN excluded.name != '' THEN excluded.name ELSE saved_chapters.name END,
                    url = excluded.url,
                    test_type = excluded.test_type,
                    question_count = CASE WHEN excluded.question_count > 0 THEN excluded.question_count ELSE saved_chapters.question_count END,
                    updated_at = excluded.updated_at
                """,
                (
                    c["id"], course_id, c["seq"], c["name"],
                    f"https://me-tp.qureo.education/chapter/{c['id']}",
                    c.get("test_type", "review"),
                    c.get("question_count", 0),
                    _now(),
                ),
            )
        conn.commit()


def get_all(course_id: str) -> list[SavedChapter]:
    rows = fetch_all(
        "SELECT * FROM saved_chapters WHERE course_id = ? ORDER BY seq",
        (course_id,),
    )
    return [
        SavedChapter(
            chapter_id=r["chapter_id"],
            course_id=r["course_id"],
            seq=r["seq"],
            name=r["name"],
            url=r["url"],
            test_type=r["test_type"],
            question_count=r["question_count"],
            completed=bool(r["completed"]),
            diamond=r["diamond"],
        )
        for r in rows
    ]


def get(chapter_id: int) -> SavedChapter | None:
    r = fetch_one("SELECT * FROM saved_chapters WHERE chapter_id = ?", (chapter_id,))
    if not r:
        return None
    return SavedChapter(
        chapter_id=r["chapter_id"],
        course_id=r["course_id"],
        seq=r["seq"],
        name=r["name"],
        url=r["url"],
        test_type=r["test_type"],
        question_count=r["question_count"],
        completed=bool(r["completed"]),
        diamond=r["diamond"],
    )


def get_first_uncompleted(course_id: str) -> SavedChapter | None:
    r = fetch_one(
        "SELECT * FROM saved_chapters WHERE course_id = ? AND completed = 0 ORDER BY seq LIMIT 1",
        (course_id,),
    )
    if not r:
        return None
    return SavedChapter(
        chapter_id=r["chapter_id"], course_id=r["course_id"], seq=r["seq"],
        name=r["name"], url=r["url"], test_type=r["test_type"],
        question_count=r["question_count"], completed=bool(r["completed"]),
        diamond=r["diamond"],
    )


def update_progress(chapter_id: int, completed: bool = True, diamond: int = 5) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE saved_chapters SET completed = ?, diamond = ?, updated_at = ? WHERE chapter_id = ?",
            (1 if completed else 0, diamond, _now(), chapter_id),
        )
        conn.commit()