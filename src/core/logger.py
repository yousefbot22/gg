"""Structured JSON logging with secret masking."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
import structlog
from src.config import settings


def _mask_secrets_processor(logger, method_name, event_dict):
    """Remove known secret fields before logging."""
    secret_keys = {
        "password", "token", "api_key", "gemini_api_key",
        "telegram_bot_token", "private_key", "credentials",
    }
    for key in list(event_dict.keys()):
        if key.lower() in secret_keys:
            event_dict[key] = "***REDACTED***"
    return event_dict


def setup_logging(log_level: str | None = None) -> None:
    """Configure structlog + stdlib logging."""
    level = getattr(logging, (log_level or settings.log_level).upper(), logging.INFO)

    # stdlib logging
    log_file = settings.logs_dir / "bot.log"
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=handlers,
        force=True,
    )

    # structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _mask_secrets_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "qureo"):
    """Get a structured logger."""
    return structlog.get_logger(name)