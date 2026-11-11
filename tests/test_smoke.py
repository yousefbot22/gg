"""Smoke tests — imports + basic sanity."""
import pytest


def test_all_modules_import():
    """Ensure every module in src/ imports cleanly."""
    import src.config
    import src.core.logger
    import src.core.security
    import src.core.exceptions
    import src.core.rate_limiter
    import src.db.connection
    import src.db.migrations
    import src.db.models
    import src.db.repositories.answers_repo
    import src.db.repositories.chapters_repo
    import src.db.repositories.users_repo
    import src.db.repositories.subscriptions_repo
    import src.db.repositories.financial_repo
    import src.solver.qureo_api
    import src.solver.qureo_client
    import src.solver.gemini_solver
    import src.solver.spx_api
    import src.solver.spx_client
    import src.solver.browser_pool
    import src.bot.states
    import src.bot.keyboards
    import src.services.session_manager
    import src.services.queue_manager
    import src.services.notification


def test_config_masks_token():
    from src.config import settings
    masked = settings.masked_token()
    assert "..." in masked
    assert settings.telegram_bot_token not in masked