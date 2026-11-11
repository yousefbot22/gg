"""Basic config tests — run with: pytest tests/"""
import os
from unittest.mock import patch
import pytest


def test_settings_requires_token():
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "ADMIN_ID": "1"}):
        from src.config import Settings
        with pytest.raises(Exception):
            Settings()


def test_settings_masks_token():
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:ABCDEF_XYZ", "ADMIN_ID": "1"}):
        from src.config import Settings
        s = Settings()
        assert s.masked_token() != s.telegram_bot_token
        assert "..." in s.masked_token()