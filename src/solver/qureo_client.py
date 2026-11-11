"""
Qureo Playwright client — per-user session wrapper.

Responsibilities:
- Acquire a BrowserContext from the shared browser_pool.
- Login to Qureo (human-emulated typing + clicking).
- Expose the page + api for the solver loop.

⚠️ Note: this module is imported by session_manager.py, so it must NOT
import from src.services or src.bot (would create circular imports).
"""
from __future__ import annotations

import asyncio
import random
from typing import Any

from playwright.async_api import BrowserContext, Page

from src.config import settings
from src.core.logger import get_logger
from src.solver.browser_pool import browser_pool
from src.solver.qureo_api import QureoAPI

log = get_logger(__name__)


class QureoClient:
    """Per-user Qureo session — holds context + page + api."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        self._ctx: BrowserContext | None = None
        self._ctx_cm = None
        self.page: Page | None = None
        self.api = QureoAPI()
        self.logged_in = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Acquire a context from the shared browser pool."""
        if self.page and not self.page.is_closed():
            return

        self._ctx_cm = browser_pool.context(self.user_id)
        self._ctx = await self._ctx_cm.__aenter__()
        self.page = await self._ctx.new_page()
        self.api.set_page(self.page)
        log.info("client_started", user_id=self.user_id)

    async def stop(self) -> None:
        """Release context back to pool."""
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception:
            pass

        try:
            if self._ctx_cm is not None:
                await self._ctx_cm.__aexit__(None, None, None)
        except Exception:
            pass

        self.page = None
        self._ctx = None
        self._ctx_cm = None
        self.logged_in = False
        log.info("client_stopped", user_id=self.user_id)

    # ------------------------------------------------------------------
    # Human emulation helpers
    # ------------------------------------------------------------------

    async def _delay(self, lo: float = 0.3, hi: float = 0.9) -> None:
        await asyncio.sleep(random.uniform(lo, hi))

    async def _human_type(self, text: str) -> None:
        if not self.page:
            return
        if len(text) > 150:
            await self.page.keyboard.insert_text(text)
            return
        for ch in text:
            await self.page.keyboard.type(ch)
            await asyncio.sleep(random.uniform(0.02, 0.07))

    async def _human_click(self, selector_or_el: Any) -> bool:
        if not self.page:
            return False
        try:
            el = selector_or_el
            if isinstance(selector_or_el, str):
                el = await self.page.query_selector(selector_or_el)
            if not el or not await el.is_visible():
                return False

            await el.scroll_into_view_if_needed()
            box = await el.bounding_box()
            if not box:
                await el.click(force=True)
                return True

            x = box["x"] + box["width"] * random.uniform(0.35, 0.65)
            y = box["y"] + box["height"] * random.uniform(0.35, 0.65)

            await self.page.mouse.move(x, y, steps=random.randint(8, 15))
            await asyncio.sleep(random.uniform(0.05, 0.12))
            await self.page.mouse.down()
            await asyncio.sleep(random.uniform(0.04, 0.09))
            await self.page.mouse.up()
            return True
        except Exception:
            try:
                if hasattr(selector_or_el, "click"):
                    await selector_or_el.click(force=True)
                    return True
            except Exception:
                pass
            return False

    async def _click_by_text(self, targets: list[str]) -> bool:
        if not self.page:
            return False
        for target in targets:
            t = (target or "").strip()
            if not t:
                continue
            try:
                loc = self.page.locator(f'text="{t}"').first
                if await loc.count() > 0 and await loc.is_visible():
                    await self._human_click(loc)
                    await asyncio.sleep(0.5)
                    return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, username: str, password: str) -> tuple[bool, str, str]:
        """
        Log in to Qureo.

        Returns:
            (success, message, screenshot_path)
        """
        await self.start()
        assert self.page is not None

        try:
            log.info("login_started", user_id=self.user_id)
            await self.page.goto(
                settings.qureo_login_url,
                wait_until="domcontentloaded",
                timeout=45000,
            )
            await self._delay(1.5, 2.5)

            # Handle "Go to Learning Login" gate
            await self._click_by_text([
                "Go to Learning Login",
                "انتقل إلى تسجيل الدخول للتعلم",
                "Learning Login",
            ])
            await self._delay(1.5, 2.0)

            # A new tab may have opened
            if self._ctx and len(self._ctx.pages) > 1:
                self.page = self._ctx.pages[-1]
                self.api.set_page(self.page)
                await self.page.bring_to_front()

            await self.page.wait_for_selector('input[type="password"]', timeout=15000)

            user_input = await self.page.query_selector(
                'input[type="text"], input[name="username"], input[name="id"], input'
            )
            pass_input = await self.page.query_selector('input[type="password"]')

            if not user_input or not pass_input:
                shot = await self._screenshot("login_fields_missing")
                return False, "لم يتم العثور على حقول الدخول", shot

            await self._human_click(user_input)
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.press("Backspace")
            await self._human_type(username)

            await self._human_click(pass_input)
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.press("Backspace")
            await self._human_type(password)

            # Submit
            if not await self._human_click('button[type="submit"]'):
                if not await self._click_by_text(["تسجيل الدخول", "Login", "دخول"]):
                    await pass_input.press("Enter")

            await asyncio.sleep(4)

            if "login" in self.page.url.lower():
                shot = await self._screenshot("login_failed")
                return False, "اسم المستخدم أو كلمة المرور غير صحيحة", shot

            self.logged_in = True
            shot = await self._screenshot("login_ok")
            log.info("login_success", user_id=self.user_id)
            return True, "تم تسجيل الدخول بنجاح!", shot

        except Exception as e:
            log.exception("login_error", user_id=self.user_id, error=str(e))
            shot = await self._screenshot("login_exception")
            return False, f"خطأ أثناء تسجيل الدخول: {e}", shot

    # ------------------------------------------------------------------
    # Course navigation
    # ------------------------------------------------------------------

    async def open_course(self, course_url: str | None = None) -> tuple[bool, str]:
        """Navigate to a course page and click Start."""
        if not self.page:
            await self.start()
        assert self.page is not None

        target = course_url or (
            f"{settings.qureo_base_url}/course/{settings.qureo_python_course_id}"
        )

        try:
            if target in (self.page.url or ""):
                await self._click_by_text(["بدء التعلم", "ابدأ", "Start", "متابعة"])
                return True, "المسار مفتوح"

            await self.page.goto(target, wait_until="domcontentloaded", timeout=45000)
            await self._delay(2.0, 3.0)
            await self._click_by_text(["بدء التعلم", "ابدأ", "Start", "متابعة"])
            return True, "تم فتح المسار"

        except Exception as e:
            log.error("open_course_failed", error=str(e))
            return False, str(e)

    # ------------------------------------------------------------------
    # Screenshot helper
    # ------------------------------------------------------------------

    async def _screenshot(self, name: str) -> str:
        """Take a screenshot and return the path (empty string on failure)."""
        if not self.page or self.page.is_closed():
            return ""
        try:
            p = (
                settings.screenshots_dir
                / f"{name}_{self.user_id}_{int(asyncio.get_event_loop().time())}.png"
            )
            await self.page.screenshot(path=str(p), full_page=False, timeout=5000)
            return str(p)
        except Exception:
            return ""