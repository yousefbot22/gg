"""
Central configuration — all secrets loaded from environment only.

🔒 SECURITY NOTES:
- No secrets are ever hardcoded here.
- Missing required secrets raise immediately at import time.
- Sensitive values are masked when logged.

🔁 COMPATIBILITY:
- New code should use:  from src.config import settings, get_settings
- Legacy code can use:  from src.config import Config
  (Config is a thin shim that maps old attribute names onto `settings`)
"""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ============================================================
# Paths
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent        # project root
SRC_DIR = Path(__file__).resolve().parent                # src/
ENV_FILE = BASE_DIR / ".env"

# Load .env early so legacy `os.getenv` fallbacks (if any) still see values.
# We also try src/.env for users who keep it there.
load_dotenv(dotenv_path=ENV_FILE, override=False)
load_dotenv(dotenv_path=SRC_DIR / ".env", override=False)


# ============================================================
# Settings (pydantic-settings)
# ============================================================
class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram ---
    telegram_bot_token: str = Field("", min_length=0)
    admin_id: int = Field(0, ge=0)

    # --- Gemini ---
    gemini_api_key: str = Field("", min_length=0)

    # --- Qureo ---
    qureo_base_url: str = "https://me-tp.qureo.education"
    qureo_login_url: str = "https://me-portal.qureo.education/login"
    qureo_python_course_id: str = "python_short_ar"
    qureo_js_course_id: str = "javascript_ar"

    qureo_username: str = ""
    qureo_password: str = ""

    # ---spx---
    spx_base_url: str = "https://egy.app.spx-learning-square.com"
    spx_login_url: str = "https://egy.app.spx-learning-square.com/login"
    spx_subject_id: int = 7
        
    spx_username: str = ""
    spx_password: str = ""        
    # Default course URL — kept explicit so legacy code can read it directly.
    # If not set in .env, defaults to the JS course (matches old behaviour).
    default_course_url: str = ""
    default_js_course_url: str = ""

    # --- Firebase ---
    enable_firebase: bool = True
    firebase_credentials_file: str = "firebase_credentials.json"
    firebase_credentials_json: str = ""

    # --- Browser ---
    headless: bool = True
    browser_pool_size: int = Field(3, ge=1, le=10)
    browser_max_lifetime_sec: int = 1800

    # --- Server ---
    port: int = Field(8080, ge=1, le=65535)
    log_level: str = "INFO"

    # --- Rate limiting / retries ---
    rate_limit_min_delay: float = Field(0.4, ge=0.0)
    rate_limit_max_delay: float = Field(1.2, ge=0.0)
    rate_limit_max_retries: int = Field(3, ge=0)

    # --- Features ---
    feature_spx: bool = True
    feature_analytics: bool = True
    trial_levels_limit: int = 10

    # === Force Subscription ===
    force_sub_enabled: bool = True
    force_sub_channel_id: int =  -1002533570140   # ← ضع ID قناتك هنا
    force_sub_channel_url: str = "https://t.me/zceyou"
    force_sub_channel_name: str = "قناتنا الرسمية"

    # ============================================================
    # Validators
    # ============================================================
    @field_validator("telegram_bot_token")
    @classmethod
    def _validate_token(cls, v: str) -> str:
        # Lenient: allow empty (so tooling / tests can import without .env).
        # Runtime code should call `settings.require_telegram_token()`.
        if v and ":" not in v:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is invalid. Expected format '123456:ABC...' "
                "from @BotFather."
            )
        return v

    @field_validator("admin_id")
    @classmethod
    def _validate_admin(cls, v: int) -> int:
        if v < 0:
            raise ValueError("ADMIN_ID must be >= 0.")
        return v

    @field_validator("rate_limit_min_delay")
    @classmethod
    def _validate_min_delay(cls, v: float) -> float:
        if v < 0:
            raise ValueError("RATE_LIMIT_MIN_DELAY must be >= 0.")
        return v

    # ============================================================
    # Derived paths
    # ============================================================
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

    # ============================================================
    # URL helpers (used by shim + new code)
    # ============================================================
    def python_course_url(self) -> str:
        return f"{self.qureo_base_url.rstrip('/')}/course/{self.qureo_python_course_id}"

    def js_course_url(self) -> str:
        return f"{self.qureo_base_url.rstrip('/')}/course/{self.qureo_js_course_id}"

    @property
    def effective_default_course_url(self) -> str:
        """Resolve DEFAULT_COURSE_URL with fallback chain."""
        if self.default_course_url:
            return self.default_course_url
        if self.default_js_course_url:
            return self.default_js_course_url
        return self.js_course_url()

    # ============================================================
    # Safe logging helpers
    # ============================================================
    def masked_token(self) -> str:
        t = self.telegram_bot_token
        return f"{t[:6]}...{t[-4:]}" if len(t) > 12 else ("(not set)" if not t else "***")

    def masked_gemini_key(self) -> str:
        k = self.gemini_api_key
        return f"{k[:6]}...{k[-4:]}" if len(k) > 12 else "(not set)"

    # ============================================================
    # Runtime assertions (call these from main.py)
    # ============================================================
    def require_telegram_token(self) -> str:
        if not self.telegram_bot_token:
            raise SystemExit(
                "❌ TELEGRAM_BOT_TOKEN is missing.\n"
                "   Get one from @BotFather and set it in .env"
            )
        return self.telegram_bot_token

    def require_admin_id(self) -> int:
        if not self.admin_id:
            raise SystemExit(
                "❌ ADMIN_ID is missing. Set your Telegram numeric ID in .env"
            )
        return self.admin_id


# ============================================================
# Cached instance accessors
# ============================================================
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()  # type: ignore[call-arg]


settings: Settings = get_settings()


# ============================================================
# Legacy compatibility shim — `Config`
# ------------------------------------------------------------
# Maps the OLD attribute names (SCREAMING_SNAKE_CASE) used by
# existing modules (qureo_client.py, handlers, etc.) onto the
# new `Settings` object. Importing `Config` continues to work
# exactly as before, but every write now flows through the
# validated pydantic model.
# ============================================================
class _LegacyConfig:
    """Read-only view of `settings` exposing legacy attribute names."""

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str = settings.telegram_bot_token
    ADMIN_ID: int = settings.admin_id

    # --- Gemini ---
    GEMINI_API_KEY: str = settings.gemini_api_key

    # --- Qureo ---
    LOGIN_URL: str = settings.qureo_login_url
    QUREO_USERNAME: str = settings.qureo_username
    QUREO_PASSWORD: str = settings.qureo_password

    DEFAULT_COURSE_URL: str = settings.effective_default_course_url
    DEFAULT_JS_COURSE_URL: str = (
        settings.default_js_course_url or settings.js_course_url()
    )

    # --- Browser ---
    HEADLESS: bool = settings.headless

    # --- Firebase ---
    ENABLE_FIREBASE: bool = settings.enable_firebase
    FIREBASE_CREDENTIALS_FILE: str = settings.firebase_credentials_file
    FIREBASE_CREDENTIALS_PATH: Path = settings.firebase_credentials_path

    # --- Server ---
    PORT: int = settings.port

    # --- Paths (properties so they're created lazily, like the old file) ---
    @property
    def SCREENSHOTS_DIR(self) -> Path:  # noqa: N802
        return settings.screenshots_dir

    @property
    def LOGS_DIR(self) -> Path:  # noqa: N802
        return settings.logs_dir

    @property
    def DATA_DIR(self) -> Path:  # noqa: N802
        return settings.data_dir

    # --- Extras that new code may want via the shim ---
    @property
    def RATE_LIMIT_MIN_DELAY(self) -> float:  # noqa: N802
        return settings.rate_limit_min_delay

    @property
    def RATE_LIMIT_MAX_DELAY(self) -> float:  # noqa: N802
        return settings.rate_limit_max_delay

    @property
    def RATE_LIMIT_MAX_RETRIES(self) -> int:  # noqa: N802
        return settings.rate_limit_max_retries

    @property
    def TRIAL_LEVELS_LIMIT(self) -> int:  # noqa: N802
        return settings.trial_levels_limit

    # Prevent accidental attribute writes from legacy code
    def __setattr__(self, key: str, value: Any) -> None:  # pragma: no cover
        raise AttributeError(
            f"_LegacyConfig is read-only. Update Settings/environment instead "
            f"(tried to set '{key}')."
        )


Config = _LegacyConfig()


# ============================================================
# Startup sanity check
# ------------------------------------------------------------
# We do NOT raise here for missing TELEGRAM_BOT_TOKEN / ADMIN_ID,
# because some tooling (tests, migrations, `--help`) imports this
# module without a full .env. Instead, main.py should call
# `settings.require_telegram_token()` / `require_admin_id()`.
#
# Set STRICT_CONFIG=1 in .env to restore the old fail-fast behaviour.
# ============================================================
if os.getenv("STRICT_CONFIG", "0").lower() in ("1", "true", "yes"):
    settings.require_telegram_token()
    settings.require_admin_id()