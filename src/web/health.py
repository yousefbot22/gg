"""
Health check server — runs alongside the bot on the same port.

Endpoints:
    GET /          -> simple 200 "ok"
    GET /health    -> detailed JSON with all subsystems
    GET /ping      -> liveness probe
    GET /ready     -> readiness probe (DB + config)
"""
from __future__ import annotations

import time
from typing import Any

from aiohttp import web

from src.core.logger import get_logger
from src.db.connection import fetch_one

log = get_logger(__name__)

_STARTED_AT = time.time()


async def _root(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "qureo-bot"})


async def _ping(request: web.Request) -> web.Response:
    return web.json_response({"pong": True})


async def _ready(request: web.Request) -> web.Response:
    """Readiness — checks DB is accessible."""
    try:
        fetch_one("SELECT 1 as x")
        return web.json_response({"ready": True})
    except Exception as e:
        return web.json_response(
            {"ready": False, "error": str(e)},
            status=503,
        )


async def _health(request: web.Request) -> web.Response:
    """Detailed health — pull state from every subsystem."""
    from src.services.session_manager import session_manager
    from src.services.queue_manager import queue_manager
    from src.solver.browser_pool import browser_pool
    from src.db.firebase.client import firebase_client

    db_ok = True
    db_error = None
    try:
        fetch_one("SELECT 1 as x")
    except Exception as e:
        db_ok = False
        db_error = str(e)

    payload: dict[str, Any] = {
        "status": "ok" if db_ok else "degraded",
        "uptime_sec": int(time.time() - _STARTED_AT),
        "version": "2.0.0",
        "db": {"ok": db_ok, "error": db_error},
        "firebase": firebase_client.health(),
        "sessions": session_manager.stats(),
        "browser_pool": browser_pool.stats(),
        "tasks_running": sum(
            1 for uid in list(queue_manager._running) if queue_manager.is_running(uid)
        ),
    }
    return web.json_response(payload)


def _build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", _root)
    app.router.add_get("/ping", _ping)
    app.router.add_get("/ready", _ready)
    app.router.add_get("/health", _health)
    return app


async def start_health_server(port: int) -> web.AppRunner:
    """Start the health server — returns runner for cleanup."""
    app = _build_app()
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    log.info("health_server_listening", port=port)
    return runner