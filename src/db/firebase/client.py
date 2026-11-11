"""
Firebase Firestore client with:
- Safe credential loading (env or file)
- Health check (JWT validation)
- Auto-reload when credential file changes
- Timeout on every operation (no hang)
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from src.config import settings
from src.core.logger import get_logger
from src.core.security import ensure_secure_file
from src.core.exceptions import FirebaseUnavailableError

log = get_logger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    _FIREBASE_AVAILABLE = True
except ImportError:
    _FIREBASE_AVAILABLE = False
    log.warning("firebase_admin_not_installed")


DEFAULT_TIMEOUT = 5.0


class FirebaseClient:
    """Thread-safe-ish Firestore client (one per process)."""

    def __init__(self) -> None:
        self._db: Any = None
        self._connected = False
        self._cred_mtime: float = 0.0
        self._last_error: str | None = None
        self._init()

    def _init(self, force: bool = False) -> None:
        if not _FIREBASE_AVAILABLE or not settings.enable_firebase:
            log.info("firebase_disabled")
            return

        cred = self._load_credential()
        if cred is None:
            return

        try:
            if force and firebase_admin._apps:
                for name in list(firebase_admin._apps):
                    firebase_admin.delete_app(firebase_admin._apps[name])

            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)

            self._validate_credentials(cred)
            self._db = firestore.client()
            self._connected = True
            self._last_error = None
            log.info("firebase_connected")
        except Exception as e:
            self._connected = False
            self._db = None
            self._last_error = str(e)
            log.warning(
                "firebase_init_failed",
                error=str(e),
                note="Falling back to SQLite.",
            )

    def _load_credential(self):
        # Priority 1: env JSON
        raw = settings.firebase_credentials_json.strip()
        if raw:
            try:
                return credentials.Certificate(json.loads(raw))
            except Exception as e:
                log.error("firebase_env_cred_invalid", error=str(e))

        # Priority 2: file
        path = settings.firebase_credentials_path
        if not path.exists():
            log.info("firebase_cred_file_missing", path=str(path))
            return None

        try:
            ensure_secure_file(path)
            self._cred_mtime = path.stat().st_mtime
            return credentials.Certificate(str(path))
        except Exception as e:
            log.error("firebase_cred_file_invalid", error=str(e))
            return None

    def _validate_credentials(self, cred) -> None:
        """Force JWT refresh synchronously to catch bad keys early."""
        try:
            import google.auth.transport.requests
            gcred = cred.get_credential() if hasattr(cred, "get_credential") else None
            if gcred and hasattr(gcred, "refresh"):
                gcred.refresh(google.auth.transport.requests.Request())
        except Exception as e:
            raise FirebaseUnavailableError(f"JWT validation failed: {e}") from e

    @property
    def is_connected(self) -> bool:
        self._maybe_reload()
        return self._connected

    def _maybe_reload(self) -> None:
        if not settings.enable_firebase:
            return
        path = settings.firebase_credentials_path
        if path.exists():
            try:
                mtime = path.stat().st_mtime
                if mtime > self._cred_mtime:
                    log.info("firebase_cred_changed_reloading")
                    self._init(force=True)
            except Exception:
                pass

    def health(self) -> dict:
        return {
            "connected": self._connected,
            "last_error": self._last_error,
            "enabled": settings.enable_firebase,
        }

    # --- Safe Firestore wrappers ---
    def set(self, collection: str, doc_id: str, data: dict, merge: bool = True) -> bool:
        if not self.is_connected:
            return False
        try:
            self._db.collection(collection).document(doc_id).set(
                {**data, "updated_at": firestore.SERVER_TIMESTAMP},
                merge=merge, timeout=DEFAULT_TIMEOUT,
            )
            return True
        except Exception as e:
            log.warning("firestore_set_failed", collection=collection, error=str(e))
            return False

    def get(self, collection: str, doc_id: str) -> dict | None:
        if not self.is_connected:
            return None
        try:
            doc = self._db.collection(collection).document(doc_id).get(timeout=DEFAULT_TIMEOUT)
            return doc.to_dict() if doc.exists else None
        except Exception as e:
            log.warning("firestore_get_failed", collection=collection, error=str(e))
            return None


firebase_client = FirebaseClient()