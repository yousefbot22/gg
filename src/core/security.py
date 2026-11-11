"""
Security utilities — sanitize, validate, and mask secrets.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from src.core.logger import get_logger

log = get_logger(__name__)

# Patterns that must never leak into logs or messages
_SECRET_PATTERNS = [
    (re.compile(r"(?i)(bot)\d{8,10}:[A-Za-z0-9_-]{30,}"), r"\1<REDACTED>"),
    (re.compile(r"(?i)(AIza)[A-Za-z0-9_-]{30,}"), r"\1<REDACTED>"),
    (re.compile(r"(?i)('|^)(private_key)('|:)(.*)"), r"\2<REDACTED>"),
]


def scrub(text: str) -> str:
    """Remove any known secret patterns from text before logging."""
    if not text:
        return text
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def safe_hash(value: str) -> str:
    """One-way hash for storing sensitive identifiers."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def validate_file_permissions(path: Path) -> bool:
    """Ensure sensitive files are not world-readable (Unix only)."""
    if not path.exists():
        return False
    try:
        mode = path.stat().st_mode
        # Only owner read/write
        return (mode & 0o077) == 0
    except Exception:
        return False


def ensure_secure_file(path: Path) -> None:
    """Try to set 0600 permissions on a sensitive file."""
    if not path.exists():
        return
    try:
        path.chmod(0o600)
        log.info("secured_file", path=str(path))
    except Exception as e:
        log.warning("chmod_failed", path=str(path), error=str(e))


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive keys in a dict."""
    sensitive = {
        "password", "token", "api_key", "gemini_api_key",
        "telegram_bot_token", "private_key", "credentials", "secret",
    }
    result = {}
    for k, v in data.items():
        if k.lower() in sensitive:
            result[k] = "***"
        elif isinstance(v, dict):
            result[k] = redact_dict(v)
        else:
            result[k] = v
    return result