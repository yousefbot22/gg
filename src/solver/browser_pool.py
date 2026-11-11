"""
Shared browser pool — reduces memory by reusing 3-5 Chromium instances
across many users. Each user gets their own isolated BrowserContext.

Architecture:
    BrowserPool
    ├── Browser #1 ─┬─ Context (user A)
    │               └─ Context (user B)
    ├── Browser #2 ─┬─ Context (user C)
    │               └─ Context (user D)
    └── Browser #3 ...

Benefits:
- 5x less memory than one-browser-per-user
- Auto-restart crashed browsers
- Graceful shutdown on app exit
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

from src.config import settings
from src.core.logger import get_logger
from src.core.exceptions import BrowserCrashedError

log = get_logger(__name__)


# Anti-detection launch args — mimics real Chrome
_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--no-first-run",
    "--no-zygote",
    "--disable-gpu",
    "--disable-crash-reporter",
    "--no-crashpad",
    "--disable-breakpad",
    "--disable-software-rasterizer",
    "--disable-extensions",
    "--disable-blink-features=AutomationControlled",
    "--lang=ar-EG,ar,en-US,en",
    "--window-size=1280,800",
]

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class PooledBrowser:
    """A browser instance tracked by the pool."""
    browser: Browser
    created_at: float = field(default_factory=time.monotonic)
    active_contexts: int = 0

    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > settings.browser_max_lifetime_sec

    def is_healthy(self) -> bool:
        try:
            return self.browser.is_connected()
        except Exception:
            return False


class BrowserPool:
    """
    Global browser pool with per-user context isolation.

    Usage:
        async with pool.context(user_id=123) as ctx:
            page = await ctx.new_page()
            ...
    """

    def __init__(self, size: int | None = None):
        self._size = size or settings.browser_pool_size
        self._playwright: Playwright | None = None
        self._browsers: list[PooledBrowser] = []
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        """Start playwright engine (does NOT launch browsers yet — lazy)."""
        async with self._lock:
            if self._started:
                return
            self._playwright = await async_playwright().start()
            self._started = True
            log.info("browser_pool_started", size=self._size)

    async def stop(self) -> None:
        """Close all browsers gracefully."""
        async with self._lock:
            for pb in self._browsers:
                try:
                    if pb.is_healthy():
                        await pb.browser.close()
                except Exception as e:
                    log.warning("browser_close_error", error=str(e))
            self._browsers.clear()

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None
            self._started = False
            log.info("browser_pool_stopped")

    async def _get_browser(self) -> PooledBrowser:
        """Pick the least-loaded healthy browser, or launch a new one."""
        # Clean up dead browsers
        self._browsers = [b for b in self._browsers if b.is_healthy() and not b.is_expired()]

        # Reuse least-loaded
        if self._browsers:
            self._browsers.sort(key=lambda b: b.active_contexts)
            chosen = self._browsers[0]
            if chosen.active_contexts < self._size * 4:  # max ~4 contexts/browser
                return chosen

        # Launch new
        if len(self._browsers) >= self._size:
            # All saturated — pick least-loaded anyway
            self._browsers.sort(key=lambda b: b.active_contexts)
            return self._browsers[0]

        await self.start()  # ensure playwright ready
        assert self._playwright is not None

        try:
            browser = await self._playwright.chromium.launch(
                headless=settings.headless,
                args=_LAUNCH_ARGS,
            )
            pb = PooledBrowser(browser=browser)
            self._browsers.append(pb)
            log.info("browser_launched", total=len(self._browsers))
            return pb
        except Exception as e:
            log.error("browser_launch_failed", error=str(e))
            # Try to install chromium once
            await self._try_install_chromium()
            raise BrowserCrashedError(f"Failed to launch browser: {e}") from e

    async def _try_install_chromium(self) -> None:
        """One-shot recovery: try installing chromium if missing."""
        import subprocess
        import sys
        log.info("attempting_chromium_install")
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False, timeout=120)
            if sys.platform != "win32":
                subprocess.run([sys.executable, "-m", "playwright", "install-deps", "chromium"], check=False, timeout=120)
        except Exception as e:
            log.error("chromium_install_failed", error=str(e))

    @asynccontextmanager
    async def context(
        self,
        user_id: int,
        viewport: dict | None = None,
    ) -> AsyncIterator[BrowserContext]:
        """
        Get an isolated BrowserContext for a user.

        The context is automatically closed and its slot freed on exit.
        """
        pb = await self._get_browser()
        pb.active_contexts += 1

        ctx = None
        try:
            ctx = await pb.browser.new_context(
                viewport=viewport or {"width": 1280, "height": 800},
                user_agent=_USER_AGENT,
                locale="ar-EG",
                timezone_id="Africa/Cairo",
                extra_http_headers={"Accept-Language": "ar-EG,ar;q=0.9,en-US;q=0.8"},
            )
            # Hide webdriver flag
            await ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            log.debug("context_created", user_id=user_id)
            yield ctx
        finally:
            if ctx is not None:
                try:
                    await ctx.close()
                except Exception as e:
                    log.warning("context_close_error", user_id=user_id, error=str(e))
            pb.active_contexts = max(0, pb.active_contexts - 1)

    def stats(self) -> dict:
        """Diagnostics for health endpoint."""
        return {
            "browsers": len(self._browsers),
            "active_contexts": sum(b.active_contexts for b in self._browsers),
            "size_limit": self._size,
        }


# Singleton
browser_pool = BrowserPool()