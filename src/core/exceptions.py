"""Custom exceptions for the application."""
from __future__ import annotations


class QureoBotError(Exception):
    """Base exception for all bot errors."""


class ConfigurationError(QureoBotError):
    """Raised when configuration is invalid."""


class AuthenticationError(QureoBotError):
    """Raised when Qureo login fails."""


class SessionExpiredError(QureoBotError):
    """Raised when user session is expired."""


class ChapterLockedError(QureoBotError):
    """Raised when a chapter is locked on Qureo side."""

    def __init__(self, chapter_id: int, message: str = "Chapter is locked"):
        self.chapter_id = chapter_id
        super().__init__(message)


class RateLimitError(QureoBotError):
    """Raised when rate limit is exceeded (possibly by Qureo)."""


class BrowserCrashedError(QureoBotError):
    """Raised when Playwright browser crashes."""


class SubscriptionError(QureoBotError):
    """Raised for subscription-related failures."""


class GroupFullError(SubscriptionError):
    """Raised when a subscription group is at capacity."""


class InvalidSubscriptionPassword(SubscriptionError):
    """Raised when subscription password is wrong."""


class TrialExhaustedError(SubscriptionError):
    """Raised when free trial levels are all used."""


class FirebaseUnavailableError(QureoBotError):
    """Raised when Firebase sync fails (non-fatal)."""