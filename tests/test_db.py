"""Database tests."""
import pytest


def test_migrations_run(tmp_db):
    from src.db.connection import fetch_one

    row = fetch_one("SELECT COUNT(*) as c FROM schema_migrations")
    assert row["c"] >= 1


def test_seed_chapters(tmp_db):
    from src.db.migrations import run_migrations
    from src.db.repositories import chapters_repo

    chapters_repo.seed_defaults()
    py = chapters_repo.get_all("python_short_ar")
    js = chapters_repo.get_all("javascript_ar")
    assert len(py) == 25
    assert len(js) == 40


def test_save_and_get_answer(tmp_db):
    from src.db.repositories import answers_repo

    answers_repo.save_choice_answer(
        question_id=100,
        chapter_id=1,
        correct_choice_id=42,
        correct_content="Correct answer",
        explanation="Because...",
        question_text="What is 2+2?",
    )
    ans = answers_repo.get_answer(100)
    assert ans is not None
    assert ans.correct_choice_id == 42
    assert ans.question_type == "choice"


def test_arabic_normalization():
    from src.db.repositories.answers_repo import normalize_arabic

    assert normalize_arabic("إجابة") == normalize_arabic("اجابة")
    assert normalize_arabic("مَسْؤُول") == normalize_arabic("مسؤول")
    assert normalize_arabic("مدرسة") == normalize_arabic("مدرسه")


def test_subscription_password_hashing(tmp_db):
    from src.db.repositories import subscriptions_repo

    subscriptions_repo.create_group("g1", "secret123", "Test Tier", 10)
    assert subscriptions_repo.verify_password("g1", "secret123") is True
    assert subscriptions_repo.verify_password("g1", "wrong") is False