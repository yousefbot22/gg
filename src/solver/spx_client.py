"""
SPX Playwright client — login + subject selection + chapter solve.
Uses shared browser_pool.
"""
from __future__ import annotations

from playwright.async_api import Page, BrowserContext

from src.core.logger import get_logger
from src.solver.browser_pool import browser_pool
from src.solver.spx_api import SPXAPI
from src.solver.gemini_solver import GeminiSolver

log = get_logger(__name__)


_SPX_LOGIN = "https://egy.app.spx-learning-square.com/login"
_SPX_CURRICULUM = "https://egy.app.spx-learning-square.com/subjects/7/curriculum"


class SPXClient:
    def __init__(self, user_id: int, gemini: GeminiSolver | None = None):
        self.user_id = user_id
        self._ctx: BrowserContext | None = None
        self.page: Page | None = None
        self.api = SPXAPI()
        self.gemini = gemini or GeminiSolver()
        self.logged_in = False

    async def start(self) -> None:
        if self.page and not self.page.is_closed():
            return
        self._ctx_cm = browser_pool.context(self.user_id)
        self._ctx = await self._ctx_cm.__aenter__()
        self.page = await self._ctx.new_page()
        self.api.set_page(self.page)
        log.info("spx_client_started", user_id=self.user_id)

    async def stop(self) -> None:
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception:
            pass
        try:
            if hasattr(self, "_ctx_cm") and self._ctx_cm:
                await self._ctx_cm.__aexit__(None, None, None)
        except Exception:
            pass
        self.page = None
        self._ctx = None
        self.logged_in = False

    async def login(self, username: str, password: str) -> tuple[bool, str, str]:
        await self.start()
        assert self.page is not None

        try:
            await self.page.goto(_SPX_LOGIN, wait_until="domcontentloaded", timeout=45000)
            await self.page.wait_for_selector('input[type="password"]', timeout=15000)

            user_input = await self.page.query_selector('input[type="text"], input')
            pass_input = await self.page.query_selector('input[type="password"]')
            if not user_input or not pass_input:
                return False, "حقول الدخول غير موجودة.", ""

            await user_input.fill(username)
            await pass_input.fill(password)
            await self.page.keyboard.press("Enter")
            await self.page.wait_for_load_state("networkidle", timeout=20000)

            if "login" in self.page.url.lower():
                return False, "بيانات الدخول غير صحيحة.", ""

            # Navigate to financial literacy curriculum
            await self.page.goto(_SPX_CURRICULUM, wait_until="domcontentloaded", timeout=30000)
            self.logged_in = True
            return True, "تم تسجيل الدخول بنجاح!", ""

        except Exception as e:
            log.error("spx_login_failed", error=str(e))
            return False, f"خطأ: {e}", ""

    async def get_dashboard(self) -> dict:
        if not self.page:
            return {}
        self.api.set_page(self.page)
        auth = await self.api.get_me()
        curriculum = await self.api.get_curriculum(7)

        total_items = 0
        completed = 0
        current = None
        for unit in curriculum:
            for sec in unit.get("sections", []):
                for item in sec.get("items", []):
                    total_items += 1
                    if item.get("is_completed"):
                        completed += 1
                    elif current is None and item.get("is_unlocked", True):
                        current = item

        pct = round(completed / total_items * 100, 1) if total_items else 0
        return {
            "student_name": auth.get("name", ""),
            "total_items": total_items,
            "completed_items": completed,
            "progress_pct": pct,
            "current_item": current,
            "curriculum": curriculum,
        }

    async def solve_chapter(self, chapter_id: int, on_progress=None) -> dict:
        if not self.page:
            return {"success": False, "message": "not_logged_in"}
        self.api.set_page(self.page)
        return await self.api.solve_chapter_with_gemini(chapter_id, self.gemini, on_progress)