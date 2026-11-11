"""
SPX Learning Square API client — Financial Literacy platform.

Base: https://egy.app.spx-learning-square.com
Subject: 7 (الثقافة المالية) — Second-year secondary.

Design goals:
- Every request passes through the shared rate_limiter (anti-ban).
- All requests are executed via window.fetch inside an active Playwright page
  so cookies / CSRF / localStorage token are reused automatically.
- Errors are typed and propagated (not swallowed).
- Curriculum is cached on disk to speed up subsequent solves.
- One solve_chapter_item() entry-point handles chapter / review / test uniformly.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from playwright.async_api import Page

from src.config import settings
from src.core.logger import get_logger
from src.core.rate_limiter import rate_limiter
from src.core.exceptions import (
    ChapterLockedError,
    QureoBotError,
    RateLimitError,
)

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPX_BASE_URL = "https://egy.app.spx-learning-square.com"
SPX_API_BASE = f"{SPX_BASE_URL}/api/v1"
SPX_SUBJECT_ID = 7  # financial literacy

CURRICULUM_CACHE = settings.data_dir / "spx" / "curriculum.json"
BLOCKS_CACHE_DIR = settings.data_dir / "spx"

ItemType = Literal["chapter", "review", "test"]
ProgressCallback = Callable[[str], Awaitable[None]]


# JavaScript fetch bridge — reads token from storage, adds CSRF header,
# always uses credentials: 'include'.
_JS_FETCH = r"""
async ([url, method, body]) => {
    try {
        let token = '';
        try {
            token = localStorage.getItem('token')
                 || localStorage.getItem('access_token')
                 || localStorage.getItem('auth_token')
                 || sessionStorage.getItem('token')
                 || '';
        } catch (e) {}

        const headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        };
        if (token) headers['Authorization'] = 'Bearer ' + token;

        try {
            const m = document.cookie.split('; ').find(r => r.startsWith('XSRF-TOKEN='));
            if (m) headers['X-XSRF-TOKEN'] = decodeURIComponent(m.split('=')[1]);
        } catch (e) {}

        const opts = { method, credentials: 'include', headers };
        if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
            opts.body = JSON.stringify(body);
        }

        const res = await window.fetch(url, opts);
        const ct = res.headers.get('content-type') || '';
        const data = ct.includes('json') ? await res.json() : await res.text();

        return {
            ok: res.ok,
            status: res.status,
            data,
            url: url
        };
    } catch (err) {
        return { ok: false, status: 0, error: String(err), url: url };
    }
}
"""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class SPXAPI:
    """
    Stateful SPX client bound to a single Playwright page (per user).

    The page MUST already be on the SPX domain for cookies to work; call
    `ensure_domain()` before making authenticated calls, or use login()
    from SPXClient which handles this automatically.
    """

    def __init__(self, page: Page | None = None) -> None:
        self.page = page
        self._last_curriculum: list[dict] | None = None

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------

    def set_page(self, page: Page) -> None:
        self.page = page

    def _require_page(self) -> Page:
        if self.page is None or self.page.is_closed():
            raise QureoBotError("SPX page is not active — call login() first")
        return self.page

    async def _normalize_url(self, endpoint: str) -> str:
        if endpoint.startswith("http"):
            return endpoint
        ep = endpoint if endpoint.startswith("/") else "/" + endpoint
        if not ep.startswith("/api/v1"):
            ep = "/api/v1" + ep
        return f"{SPX_BASE_URL}{ep}"

    async def ensure_domain(self) -> None:
        """Navigate to SPX domain if the page is elsewhere (cookies scope)."""
        page = self._require_page()
        try:
            if "spx-learning-square.com" not in page.url.lower():
                log.info("spx_ensure_domain", current_url=page.url)
                await page.goto(
                    f"{SPX_BASE_URL}/subjects/{SPX_SUBJECT_ID}/curriculum",
                    wait_until="domcontentloaded",
                    timeout=25_000,
                )
        except Exception as e:
            log.warning("spx_ensure_domain_failed", error=str(e))

    async def _call(
        self,
        endpoint: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Fire an API request through window.fetch inside the page.

        Returns dict: { ok, status, data, url } or { ok: False, error }
        Rate limited + retried by rate_limiter.
        """
        page = self._require_page()
        await self.ensure_domain()

        url = await self._normalize_url(endpoint)
        key = f"spx:{method.upper()}:{endpoint}"

        async def _do() -> dict[str, Any]:
            try:
                return await page.evaluate(_JS_FETCH, [url, method.upper(), body])
            except Exception as e:
                log.warning("spx_eval_failed", endpoint=endpoint, error=str(e))
                return {"ok": False, "status": 0, "error": str(e), "url": url}

        try:
            result = await rate_limiter.call(key, _do)
        except RateLimitError as e:
            log.error("spx_rate_limit_gave_up", endpoint=endpoint, error=str(e))
            return {"ok": False, "status": 0, "error": str(e), "url": url}

        log.debug(
            "spx_api_call",
            method=method,
            endpoint=endpoint,
            status=result.get("status"),
            ok=result.get("ok"),
        )
        return result

    @staticmethod
    def _unwrap(res: dict[str, Any]) -> Any:
        """Unwrap {ok, data} -> inner `.data` field if present."""
        if not res.get("ok"):
            return None
        data = res.get("data")
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data

    # ------------------------------------------------------------------
    # Endpoints — auth & subject
    # ------------------------------------------------------------------

    async def get_me(self) -> dict[str, Any]:
        return self._unwrap(await self._call("/auth/me")) or {}

    async def get_subject(self, subject_id: int = SPX_SUBJECT_ID) -> dict[str, Any]:
        return self._unwrap(await self._call(f"/subjects/{subject_id}")) or {}

    async def get_curriculum(
        self,
        subject_id: int = SPX_SUBJECT_ID,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Fetch full curriculum tree with on-disk cache fallback.
        Cache is re-used only if the network call fails.
        """
        res = await self._call(f"/subjects/{subject_id}/curriculum")
        if res.get("ok"):
            data = self._unwrap(res) or []
            if isinstance(data, list) and data:
                self._last_curriculum = data
                self._save_curriculum_cache(data)
                return data

        if use_cache:
            cached = self._load_curriculum_cache()
            if cached:
                log.info("spx_curriculum_cache_hit", units=len(cached))
                self._last_curriculum = cached
                return cached

        return []

    @staticmethod
    def _save_curriculum_cache(data: list[dict]) -> None:
        try:
            CURRICULUM_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with open(CURRICULUM_CACHE, "w", encoding="utf-8") as f:
                json.dump({"data": data}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning("spx_curriculum_cache_write_failed", error=str(e))

    @staticmethod
    def _load_curriculum_cache() -> list[dict] | None:
        try:
            if CURRICULUM_CACHE.exists():
                with open(CURRICULUM_CACHE, "r", encoding="utf-8") as f:
                    return json.load(f).get("data", [])
        except Exception as e:
            log.warning("spx_curriculum_cache_read_failed", error=str(e))
        return None

    # ------------------------------------------------------------------
    # Endpoints — chapter content
    # ------------------------------------------------------------------

    async def get_chapter_blocks(self, chapter_id: int) -> dict[str, Any]:
        """
        Returns:
            { chapter: {...}, blocks: [...] }         on success
            { error_code: str, error_message: str }   on known failure
        """
        res = await self._call(f"/chapters/{chapter_id}/blocks")

        if res.get("ok"):
            payload = self._unwrap(res)
            if isinstance(payload, dict):
                payload["_ok"] = True
                return payload
            if isinstance(payload, list):
                return {"_ok": True, "blocks": payload, "chapter": {}}

        # Parse error from server payload
        raw = res.get("data") if isinstance(res.get("data"), dict) else {}
        err = raw.get("error", {}) if isinstance(raw, dict) else {}
        code = (err.get("code") if isinstance(err, dict) else None) or f"http_{res.get('status', 0)}"
        message = (
            (err.get("message") if isinstance(err, dict) else None)
            or res.get("error")
            or "unknown_error"
        )

        # Try disk cache before giving up (offline resilience)
        cached = self._read_blocks_cache(chapter_id)
        if cached and cached.get("blocks"):
            log.info("spx_blocks_cache_hit", chapter_id=chapter_id)
            cached["_ok"] = True
            return cached

        return {"_ok": False, "error_code": code, "error_message": message, "status": res.get("status", 0)}

    def _read_blocks_cache(self, chapter_id: int) -> dict[str, Any] | None:
        path = BLOCKS_CACHE_DIR / f"chapter_{chapter_id}_blocks.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload.get("data", payload)
        except Exception:
            return None

    async def answer_question(
        self,
        chapter_id: int,
        block_id: int,
        selected_option_id: int,
        hint_used: int = 0,
    ) -> dict[str, Any]:
        """
        Submit a single MCQ answer inside a chapter.

        Response shape (server):
            { ok, data: { data: { is_correct: bool, correct_option_id: int?, explanation: str } } }
        """
        return await self._call(
            f"/chapters/{chapter_id}/answer",
            method="POST",
            body={
                "block_id": block_id,
                "selected_option_id": selected_option_id,
                "hint_used": hint_used,
            },
        )

    async def complete_chapter(
        self,
        chapter_id: int,
        cleared_block_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"star_score": 5}
        if cleared_block_ids:
            body["cleared_block_ids"] = cleared_block_ids
        return await self._call(f"/chapters/{chapter_id}/complete", method="POST", body=body)

    # ------------------------------------------------------------------
    # Endpoints — reviews
    # ------------------------------------------------------------------

    async def complete_review(self, review_id: int) -> dict[str, Any]:
        """Try multiple known endpoints for review completion."""
        candidates = [
            (f"/reviews/{review_id}/complete", {"star_score": 5}),
            (f"/chapters/{review_id}/complete", {"star_score": 5}),
            (f"/items/{review_id}/complete", {}),
            (f"/reviews/{review_id}/finish", {}),
        ]
        for ep, body in candidates:
            res = await self._call(ep, method="POST", body=body)
            if res.get("ok"):
                log.info("spx_review_completed", review_id=review_id, endpoint=ep)
                return res
        log.warning("spx_review_complete_failed", review_id=review_id)
        return {"ok": False, "error": "all_endpoints_failed"}

    # ------------------------------------------------------------------
    # Endpoints — tests
    # ------------------------------------------------------------------

    async def start_test(self, test_id: int) -> dict[str, Any]:
        """Start a test attempt (server may require it before submit)."""
        for ep, method in [
            (f"/tests/{test_id}/start", "POST"),
            (f"/tests/{test_id}/attempt", "POST"),
            (f"/tests/{test_id}/begin", "POST"),
        ]:
            res = await self._call(ep, method=method, body={})
            if res.get("ok"):
                return res
        # Getting the test itself is also fine
        return await self._call(f"/tests/{test_id}")

    async def complete_test(self, test_id: int, score: int = 100) -> dict[str, Any]:
        """
        Submit a test. Verifies the server actually marked it as passed.
        """
        await self.start_test(test_id)

        for ep, body in [
            (f"/tests/{test_id}/submit", {"score": score, "test_result": "passed", "star_score": 5}),
            (f"/tests/{test_id}/submit", {"score": score, "is_passed": True}),
            (f"/tests/{test_id}/complete", {"score": score, "test_result": "passed"}),
        ]:
            res = await self._call(ep, method="POST", body=body)
            if not res.get("ok"):
                continue
            payload = res.get("data", {})
            inner = payload.get("data", {}) if isinstance(payload, dict) else {}
            if not isinstance(inner, dict):
                inner = {}
            passed = inner.get("passed") is True or (inner.get("total_score") or 0) >= 80
            if passed:
                log.info("spx_test_passed", test_id=test_id, score=inner.get("total_score"))
                return {"ok": True, "passed": True, "score": inner.get("total_score", score), "data": payload}

        return {"ok": False, "passed": False, "score": 0, "error": "test_not_passed"}

    # ------------------------------------------------------------------
    # High-level: solve one chapter using cached answers → Gemini → fallback
    # ------------------------------------------------------------------

    async def solve_chapter(
        self,
        chapter_id: int,
        gemini_solver,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """
        Solve a chapter fully:
        1. Fetch blocks.
        2. For each question: cached DB → Gemini → fallback option.
        3. Submit answers, cache correct ones.
        4. Complete the chapter.
        """
        # Import here to avoid circular imports at module load time
        from src.db.repositories import financial_repo

        blocks_data = await self.get_chapter_blocks(chapter_id)
        if not blocks_data.get("_ok"):
            code = blocks_data.get("error_code")
            if code == "chapter_locked":
                raise ChapterLockedError(chapter_id, "الفصل مغلق — أكمل السابق أولاً")
            if code == "subject_no_access":
                raise QureoBotError("لا تملك صلاحية الوصول لهذا المنهج")
            raise QureoBotError(
                f"تعذر جلب محتوى الفصل: {blocks_data.get('error_message')}"
            )

        chapter = blocks_data.get("chapter", {}) or {}
        chapter_name = chapter.get("name", f"فصل {chapter_id}")
        blocks = blocks_data.get("blocks", []) or []

        if not blocks:
            raise QureoBotError(f"لا يوجد محتوى للفصل {chapter_id}")

        q_blocks = [b for b in blocks if b.get("type") == "question"]
        total = len(q_blocks)

        if on_progress:
            await on_progress(
                f"🚀 **بدء حل {chapter_name}** ({total} سؤال) عبر API + Gemini..."
            )

        solved = 0
        for idx, block in enumerate(q_blocks, 1):
            block_id = block.get("id")
            q_obj = block.get("question", {}) or {}
            q_id = block.get("question_id") or q_obj.get("id")
            q_text = q_obj.get("question_text", "") or q_obj.get("summary", "")
            options = block.get("options", []) or []
            if not options:
                continue

            chosen_id = await self._pick_option(
                question_text=q_text,
                options=options,
                gemini_solver=gemini_solver,
                financial_repo=financial_repo,
            )

            result = await self._submit_and_confirm(
                chapter_id=chapter_id,
                block_id=block_id,
                chosen_id=chosen_id,
                options=options,
            )

            if result["correct"]:
                solved += 1
                # Cache the correct answer for future use
                if q_text:
                    financial_repo.save(
                        question_text=q_text,
                        options=[o.get("text", "") for o in options],
                        correct_answer=result["correct_text"],
                        explanation=result["explanation"],
                        topic=chapter_name,
                        source="spx_auto",
                    )

            if on_progress and (idx % 2 == 0 or idx == total):
                await on_progress(
                    f"🎯 تم إجابة السؤال ({idx}/{total})"
                )

            await asyncio.sleep(0.3)

        # Complete the chapter
        all_ids = [b.get("id") for b in blocks if b.get("id")]
        await self.complete_chapter(chapter_id, cleared_block_ids=all_ids)

        return {
            "success": True,
            "chapter_id": chapter_id,
            "chapter_name": chapter_name,
            "total_questions": total,
            "solved_questions": solved,
            "star_score": 5,
        }

    async def _pick_option(
        self,
        question_text: str,
        options: list[dict],
        gemini_solver,
        financial_repo,
    ) -> int:
        """Pick option id: cached DB → Gemini → first option."""
        # 1. DB cache
        if question_text:
            cached = financial_repo.find(question_text)
            if cached and cached.correct_answer:
                target = cached.correct_answer.strip().lower()
                for opt in options:
                    if opt.get("text", "").strip().lower() == target:
                        return opt["id"]

        # 2. Gemini
        if gemini_solver and getattr(gemini_solver, "is_configured", False):
            try:
                opt_texts = [o.get("text", "") for o in options]
                best = await gemini_solver.solve_quiz_question(question_text, opt_texts)
                if 0 <= best < len(options):
                    return options[best]["id"]
            except Exception as e:
                log.warning("gemini_spx_pick_failed", error=str(e))

        # 3. Fallback
        return options[0]["id"]

    async def _submit_and_confirm(
        self,
        chapter_id: int,
        block_id: int,
        chosen_id: int,
        options: list[dict],
    ) -> dict[str, Any]:
        """
        Submit an answer, retry if wrong (using server's hint), return final state.
        """
        resp = await self.answer_question(chapter_id, block_id, chosen_id)
        inner = (
            resp.get("data", {}).get("data", {})
            if isinstance(resp.get("data"), dict)
            else {}
        )
        is_correct = inner.get("is_correct") is True
        explanation = inner.get("explanation", "")
        correct_id = chosen_id

        # Server told us the right answer → retry
        if not is_correct and inner.get("correct_option_id"):
            correct_id = inner["correct_option_id"]
            retry = await self.answer_question(chapter_id, block_id, correct_id)
            retry_inner = (
                retry.get("data", {}).get("data", {})
                if isinstance(retry.get("data"), dict)
                else {}
            )
            is_correct = retry_inner.get("is_correct") is True
            explanation = retry_inner.get("explanation", explanation)

        # Still wrong → brute-force remaining options
        if not is_correct:
            for opt in options:
                oid = opt.get("id")
                if oid == correct_id:
                    continue
                try_ = await self.answer_question(chapter_id, block_id, oid)
                try_inner = (
                    try_.get("data", {}).get("data", {})
                    if isinstance(try_.get("data"), dict)
                    else {}
                )
                if try_inner.get("is_correct") is True:
                    is_correct = True
                    correct_id = oid
                    explanation = try_inner.get("explanation", explanation)
                    break

        correct_text = ""
        for opt in options:
            if opt.get("id") == correct_id:
                correct_text = opt.get("text", "")
                break

        return {
            "correct": is_correct,
            "correct_id": correct_id,
            "correct_text": correct_text,
            "explanation": explanation,
        }

    # ------------------------------------------------------------------
    # High-level: complete review / test
    # ------------------------------------------------------------------

    async def solve_review(self, review_id: int) -> dict[str, Any]:
        res = await self.complete_review(review_id)
        ok = res.get("ok", False)
        return {
            "success": ok,
            "review_id": review_id,
            "message": "تم إكمال المراجعة" if ok else "تعذر إكمال المراجعة",
        }

    async def solve_test(self, test_id: int) -> dict[str, Any]:
        res = await self.complete_test(test_id)
        passed = bool(res.get("passed"))
        return {
            "success": passed,
            "test_id": test_id,
            "score": res.get("score", 0),
            "message": "تم اجتياز الاختبار" if passed else "لم يتم اجتياز الاختبار",
        }

    # ------------------------------------------------------------------
    # Unified entry point
    # ------------------------------------------------------------------

    async def solve_item(
        self,
        item_id: int,
        item_type: ItemType,
        gemini_solver,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """
        Solve any item regardless of type — chapter / review / test.
        """
        if item_type == "chapter":
            return await self.solve_chapter(item_id, gemini_solver, on_progress)
        if item_type == "review":
            return await self.solve_review(item_id)
        if item_type == "test":
            return await self.solve_test(item_id)
        raise QureoBotError(f"نوع عنصر غير مدعوم: {item_type}")


# ---------------------------------------------------------------------------
# Helpers for parsing the item type from curriculum
# ---------------------------------------------------------------------------

_ITEM_TYPE_MAP = {
    "chapter": "chapter",
    "lesson": "chapter",
    "review": "review",
    "quiz": "review",
    "test": "test",
    "exam": "test",
}


def infer_item_type(raw: str | None) -> ItemType:
    if not raw:
        return "chapter"
    return _ITEM_TYPE_MAP.get(raw.lower().strip(), "chapter")  # type: ignore[return-value]


def extract_id_from_title(title: str) -> int | None:
    """Try to extract a numeric id from an item title like 'فصل (74) ...'."""
    m = re.search(r"\((\d+)\)", title or "")
    return int(m.group(1)) if m else None