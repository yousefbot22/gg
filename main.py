"""
Qureo Solution Bot — Main entry point.

Responsibilities:
- Load config (fails fast if missing secrets).
- Setup logging.
- Initialize DB (migrations run on import).
- Start health server.
- Start Telegram polling.
- Handle graceful shutdown (SIGINT, SIGTERM).
"""
from __future__ import annotations

import asyncio
import signal
import sys
from contextlib import suppress

# Windows event loop fix (must be before any asyncio usage)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import settings
from src.core.logger import setup_logging, get_logger
from src.bot.dispatcher import build_dispatcher
from src.bot.handlers.common import COMMANDS
from src.services.queue_manager import queue_manager
from src.services.session_manager import session_manager
from src.solver.browser_pool import browser_pool
from src.web.health import start_health_server

log = get_logger("main")


async def _session_cleanup_loop(interval_sec: int = 600) -> None:
    """Periodically evict idle sessions."""
    while True:
        try:
            await asyncio.sleep(interval_sec)
            await session_manager.cleanup_idle()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("cleanup_loop_error", error=str(e))


async def _run() -> None:
    setup_logging()

    log.info(
        "starting",
        version="2.0.0",
        admin_id=settings.admin_id,
        headless=settings.headless,
        firebase=settings.enable_firebase,
        pool_size=settings.browser_pool_size,
    )

    # 1. Health server (must be up before everything else)
    health_runner = None
    try:
        health_runner = await start_health_server(settings.port)
        log.info("health_server_started", port=settings.port)
    except Exception as e:
        log.error("health_server_failed", error=str(e))

    # 2. Browser pool warmup (optional — fails silently)
    try:
        await browser_pool.start()
    except Exception as e:
        log.warning("browser_pool_warmup_failed", error=str(e))

    # 3. Bot + dispatcher
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = build_dispatcher()

    # 4. Register commands
    try:
        await bot.set_my_commands(COMMANDS)
    except Exception as e:
        log.warning("set_commands_failed", error=str(e))

    # 5. Setup graceful shutdown
    stop_event = asyncio.Event()

    def _handle_signal(sig: int) -> None:
        log.info("signal_received", signal=sig)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _handle_signal, sig)

    # 6. Start background tasks
    cleanup_task = asyncio.create_task(_session_cleanup_loop())

    # 7. Fetch bot info
    try:
        me = await bot.get_me()
        log.info("bot_ready", username=me.username)
    except Exception as e:
        log.error("get_me_failed", error=str(e))
        await bot.session.close()
        return

    # 8. Start polling (until stop_event)
    polling_task = asyncio.create_task(dp.start_polling(bot))

    await stop_event.wait()
    log.info("shutting_down")

    # Graceful teardown
    polling_task.cancel()
    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await polling_task
    with suppress(asyncio.CancelledError):
        await cleanup_task

    await queue_manager.shutdown()
    await session_manager.close_all()
    await browser_pool.stop()
    await bot.session.close()

    if health_runner:
        with suppress(Exception):
            await health_runner.cleanup()

    log.info("shutdown_complete")


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # Logger may not be configured yet
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()