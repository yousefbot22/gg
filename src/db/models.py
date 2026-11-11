"""Typed models matching DB tables."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(slots=True)
class SavedAnswer:
    question_id: int
    chapter_id: int
    question_type: Literal["choice", "description"]
    correct_choice_id: int | None = None
    correct_content: str = ""
    model_answer: str = ""
    explanation: str = ""
    question_text: str = ""
    confidence: float = 1.0
    success_count: int = 0
    updated_at: datetime | None = None


@dataclass(slots=True)
class SavedChapter:
    chapter_id: int
    course_id: str
    seq: int
    name: str = ""
    url: str = ""
    test_type: Literal["review", "test"] = "review"
    question_count: int = 0
    completed: bool = False
    diamond: int = 0
    updated_at: datetime | None = None

    @property
    def clean_url(self) -> str:
        return f"https://me-tp.qureo.education/chapter/{self.chapter_id}"


@dataclass(slots=True)
class BotUser:
    user_id: int
    grade: str = "grade_1"
    subject: str = "programming"
    active_course_url: str | None = None
    is_admin: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class SubscriptionGroup:
    group_id: str
    password_hash: str
    tier_name: str
    max_users: int
    is_active: bool = True
    created_at: datetime | None = None
    # computed
    members_count: int = 0
    completed_count: int = 0

    # ✅ حقول جديدة لدعم الباسورد لمرة واحدة
    is_one_time: bool = False
    used_by_user_id: int | None = None
    used_at: datetime | None = None

    @property
    def remaining_seats(self) -> int:
        return max(0, self.max_users - self.completed_count)

    @property
    def is_consumed(self) -> bool:
        """هل الباسورد استُهلك (للمرة الواحدة فقط)."""
        return self.is_one_time and self.used_by_user_id is not None


@dataclass(slots=True)
class GroupMember:
    group_id: str
    user_id: int
    student_username: str | None = None
    joined_at: datetime | None = None


@dataclass(slots=True)
class CompletedStudent:
    group_id: str
    student_username: str
    grade: str = ""
    completed_at: datetime | None = None


@dataclass(slots=True)
class FinancialQuestion:
    id: int
    question_text: str
    question_hash: str
    options: list[str] = field(default_factory=list)
    correct_answer: str = ""
    explanation: str = ""
    topic: str = ""
    user_id: int | None = None
    source: str = "user_training"
    confidence: float = 1.0
    created_at: datetime | None = None
    Group = SubscriptionGroup