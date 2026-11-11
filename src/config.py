"""
Central configuration — all secrets loaded from environment only.

🔒 SECURITY NOTES:
- No secrets are ever hardcoded here.
- Missing required secrets raise immediately at import time.
- Sensitive values are masked when logged.
"""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram ---
    telegram_bot_token: str = Field(..., min_length=20)
    admin_id: int = Field(..., gt=0)

    # --- Gemini ---
    gemini_api_key: str = Field("", min_length=0)

    # --- Qureo ---
    qureo_base_url: str = "https://me-tp.qureo.education"
    qureo_login_url: str = "https://me-portal.qureo.education/login"
    qureo_python_course_id: str = "python_short_ar"
    qureo_js_course_id: str = "javascript_ar"

    # --- Firebase ---
    enable_firebase: bool = False
    firebase_credentials_file: str = "firebase_credentials.json"
    firebase_credentials_json: str = ""

    # --- Browser ---
    headless: bool = True
    browser_pool_size: int = Field(3, ge=1, le=10)
    browser_max_lifetime_sec: int = 1800

    # --- Server ---
    port: int = Field(8080, ge=1, le=65535)
    log_level: str = "INFO"

    # --- Rate limiting ---
    rate_limit_min_delay: float = 0.4
    rate_limit_max_delay: float = 1.2
    rate_limit_max_retries: int = 3

    # --- Features ---
    feature_spx: bool = True
    feature_analytics: bool = True
    trial_levels_limit: int = 10

    @field_validator("telegram_bot_token")
    @classmethod
    def validate_token(cls, v: str) -> str:
        if not v or ":" not in v:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is invalid or missing. "
                "Get one from @BotFather and set it in .env"
            )
        return v

    @field_validator("admin_id")
    @classmethod
    def validate_admin(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ADMIN_ID must be a positive integer.")
        return v

    # --- Derived paths ---
    @property
    def base_dir(self) -> Path:
        return BASE_DIR

    @property
    def data_dir(self) -> Path:
        p = BASE_DIR / "data"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def logs_dir(self) -> Path:
        p = BASE_DIR / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def screenshots_dir(self) -> Path:
        p = BASE_DIR / "screenshots"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def firebase_credentials_path(self) -> Path:
        p = Path(self.firebase_credentials_file)
        return p if p.is_absolute() else BASE_DIR / p

    # --- Safe logging helpers ---
    def masked_token(self) -> str:
        t = self.telegram_bot_token
        return f"{t[:6]}...{t[-4:]}" if len(t) > 12 else "***"

    def masked_gemini_key(self) -> str:
        k = self.gemini_api_key
        return f"{k[:6]}...{k[-4:]}" if len(k) > 12 else "(not set)"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()  # type: ignore[call-arg]


# Convenience: raise immediately if misconfigured
try:
    settings = get_settings()
except Exception as e:
    raise SystemExit(
        f"❌ Configuration error: {e}\n"
        f"   Please check your .env file against .env.example"
    ) from e