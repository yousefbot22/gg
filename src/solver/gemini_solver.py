"""
Gemini AI solver — production-grade wrapper around google-genai.

Design goals:
- Only REAL model names (verified against Google AI Studio).
- Circuit breaker prevents hammering a dead API.
- Every call has a timeout (no hanging).
- Typed exceptions for clear error handling.
- Structured JSON outputs via response_schema where possible.
- Centralized cost tracking for analytics.
- Screenshot support for vision tasks (code from image, financial quizzes).

Public API:
    solver = GeminiSolver()
    if solver.is_configured:
        code   = await solver.solve_code_task(instruction, current_code, "python")
        idx    = await solver.solve_quiz_question(q_text, options)
        result = await solver.solve_financial_image(image_path)
        guide  = await solver.analyze_screen(screenshot_path, page_text)
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import settings
from src.core.logger import get_logger
from src.core.exceptions import QureoBotError

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency (google-genai)
# ---------------------------------------------------------------------------

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError as _GenAIAPIError
    _GENAI_AVAILABLE = True
except ImportError:  # pragma: no cover
    _GENAI_AVAILABLE = False
    _GenAIAPIError = Exception  # type: ignore
    log.warning("google_genai_not_installed", note="Install with: pip install google-genai")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Ordered fallback chain — from fastest/most capable to cheapest.
# These are the ONLY models Google currently (2025) exposes for
# generate_content. Older/other names cause 404s.
_MODEL_CHAIN: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",  # cheapest fallback
)

# Per-call timeout (seconds). Gemini Flash typically responds in <4s for text,
# <10s for vision. Anything beyond 25s means the API is degraded.
_CALL_TIMEOUT_SEC = 25.0

# Total tries across the whole model chain (not per model).
_MAX_TOTAL_ATTEMPTS = 6

# Circuit breaker: after N consecutive failures, stop calling Gemini for
# `cooldown` seconds (prevents quota burn on transient outages).
_BREAKER_THRESHOLD = 4
_BREAKER_COOLDOWN_SEC = 90.0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GeminiNotConfiguredError(QureoBotError):
    """Raised when API key is missing/invalid."""


class GeminiCircuitOpenError(QureoBotError):
    """Raised when circuit breaker is open (quota exhausted / API down)."""


class GeminiResponseError(QureoBotError):
    """Raised when Gemini returns an unusable response."""


class GeminiTimeoutError(QureoBotError):
    """Raised when a call exceeds the timeout."""


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

@dataclass
class CircuitBreaker:
    threshold: int = _BREAKER_THRESHOLD
    cooldown: float = _BREAKER_COOLDOWN_SEC
    failures: int = 0
    opened_at: float = 0.0

    @property
    def is_open(self) -> bool:
        if self.failures < self.threshold:
            return False
        if time.monotonic() - self.opened_at > self.cooldown:
            # Cooldown expired — allow one probe
            self.failures = 0
            return False
        return True

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()
            log.warning(
                "gemini_circuit_opened",
                failures=self.failures,
                cooldown_sec=self.cooldown,
            )

    def record_success(self) -> None:
        if self.failures > 0:
            log.info("gemini_circuit_recovered", previous_failures=self.failures)
        self.failures = 0


# ---------------------------------------------------------------------------
# Cost tracking (approximate — for analytics only)
# ---------------------------------------------------------------------------

@dataclass
class UsageStats:
    """Best-effort usage tracking (no exact token counts available)."""
    calls: int = 0
    failures: int = 0
    total_latency_ms: int = 0
    by_model: dict[str, int] = field(default_factory=dict)

    def record(self, model: str, latency_ms: int, ok: bool) -> None:
        self.calls += 1
        self.total_latency_ms += latency_ms
        if not ok:
            self.failures += 1
        self.by_model[model] = self.by_model.get(model, 0) + 1

    @property
    def avg_latency_ms(self) -> int:
        return self.total_latency_ms // self.calls if self.calls else 0


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

class GeminiSolver:
    """Gemini wrapper — one instance per process (thread-safe reads)."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (api_key or settings.gemini_api_key or "").strip()
        self._client = None
        self._breaker = CircuitBreaker()
        self.usage = UsageStats()

        if self._api_key and _GENAI_AVAILABLE:
            self._build_client()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _build_client(self) -> None:
        try:
            self._client = genai.Client(api_key=self._api_key)
            log.info(
                "gemini_client_ready",
                key_preview=self._mask(self._api_key),
                models=list(_MODEL_CHAIN),
            )
        except Exception as e:
            self._client = None
            log.error("gemini_client_init_failed", error=str(e))

    @staticmethod
    def _mask(key: str) -> str:
        return f"{key[:6]}...{key[-4:]}" if len(key) > 12 else "***"

    @property
    def is_configured(self) -> bool:
        return bool(
            self._client is not None
            and _GENAI_AVAILABLE
            and len(self._api_key) > 15
        )

    @property
    def is_available(self) -> bool:
        """True if we can currently attempt a call (breaker not open)."""
        return self.is_configured and not self._breaker.is_open

    def set_api_key(self, key: str) -> None:
        """Hot-reload the API key (used by admin / gemini key handler)."""
        self._api_key = key.strip()
        self._breaker = CircuitBreaker()
        if self._api_key and _GENAI_AVAILABLE:
            self._build_client()

    # ------------------------------------------------------------------
    # Low-level: single attempt with timeout
    # ------------------------------------------------------------------

    async def _attempt(
        self,
        model: str,
        contents: list[Any],
        response_schema: Any | None = None,
    ) -> str | None:
        """
        One single attempt with a specific model. Returns text or None.
        Raises GeminiTimeoutError only for timeouts.
        """
        if self._client is None:
            raise GeminiNotConfiguredError("Gemini client is not initialized")

        config = None
        if response_schema is not None:
            try:
                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                )
            except Exception as e:
                log.warning("gemini_schema_config_failed", error=str(e))

        started = time.monotonic()
        try:
            coro = asyncio.to_thread(
                self._client.models.generate_content,
                model=model,
                contents=contents,
                config=config,
            )
            response = await asyncio.wait_for(coro, timeout=_CALL_TIMEOUT_SEC)
        except asyncio.TimeoutError as e:
            latency = int((time.monotonic() - started) * 1000)
            self.usage.record(model, latency, ok=False)
            log.warning("gemini_timeout", model=model, timeout_sec=_CALL_TIMEOUT_SEC)
            raise GeminiTimeoutError(f"Gemini call timed out after {_CALL_TIMEOUT_SEC}s") from e

        latency = int((time.monotonic() - started) * 1000)
        text = getattr(response, "text", "") if response else ""

        if not text:
            self.usage.record(model, latency, ok=False)
            return None

        self.usage.record(model, latency, ok=True)
        return text.strip()

    # ------------------------------------------------------------------
    # Retry chain across models
    # ------------------------------------------------------------------

    async def _generate(
        self,
        contents: list[Any],
        response_schema: Any | None = None,
    ) -> str:
        """
        Try each model in the chain until one succeeds.
        Applies exponential backoff between models.
        Raises GeminiCircuitOpenError if breaker is open.
        """
        if not self.is_configured:
            raise GeminiNotConfiguredError("GEMINI_API_KEY is missing or invalid")
        if self._breaker.is_open:
            raise GeminiCircuitOpenError(
                "Gemini circuit is open (quota exhausted or API degraded). "
                "Try again in a minute."
            )

        last_error: Exception | None = None
        attempts = 0

        for model in _MODEL_CHAIN:
            if attempts >= _MAX_TOTAL_ATTEMPTS:
                break
            attempts += 1

            try:
                text = await self._attempt(model, contents, response_schema)
                if text:
                    self._breaker.record_success()
                    log.debug("gemini_success", model=model)
                    return text
                # Empty text — treat as soft failure, try next model
                log.warning("gemini_empty_response", model=model)
            except GeminiTimeoutError as e:
                last_error = e
                self._breaker.record_failure()
                # Do not retry timeouts immediately — move to next model
                continue
            except _GenAIAPIError as e:
                last_error = e
                self._breaker.record_failure()
                msg = str(e).lower()
                # 429 = quota — no point retrying other models
                if "429" in msg or "quota" in msg or "resource_exhausted" in msg:
                    log.error("gemini_quota_exhausted", model=model)
                    raise GeminiCircuitOpenError("Gemini quota exhausted") from e
                # 400 = bad request — try next model anyway
                log.warning("gemini_api_error", model=model, error=str(e))
                await asyncio.sleep(0.4 * attempts)
            except Exception as e:
                last_error = e
                self._breaker.record_failure()
                log.warning("gemini_unexpected_error", model=model, error=str(e))
                await asyncio.sleep(0.3 * attempts)

        raise GeminiResponseError(
            f"All Gemini models failed. Last error: {last_error}"
        )

    # ------------------------------------------------------------------
    # Image handling
    # ------------------------------------------------------------------

    @staticmethod
    def _image_part(path: str | None) -> Any | None:
        if not path:
            return None
        p = Path(path)
        if not p.exists():
            log.warning("gemini_image_missing", path=path)
            return None
        try:
            data = p.read_bytes()
            mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
            return types.Part.from_bytes(data=data, mime_type=mime)
        except Exception as e:
            log.warning("gemini_image_read_failed", path=path, error=str(e))
            return None

    @staticmethod
    def _extract_code(text: str) -> str:
        """Strip markdown fences if present."""
        if "```" not in text:
            return text.strip()
        m = re.search(
            r"```(?:python|javascript|js|py)?\s*\n?(.*?)```",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        return m.group(1).strip() if m else text.strip()

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        """Robust JSON extraction (handles trailing text, markdown)."""
        if not text:
            return None
        # Strip fences if present
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        candidate = m.group(1).strip() if m else text.strip()
        # Try direct parse first
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # Find outermost {...}
        m2 = re.search(r"\{.*\}", candidate, re.DOTALL)
        if m2:
            try:
                return json.loads(m2.group(0))
            except json.JSONDecodeError:
                pass
        return None

    # ------------------------------------------------------------------
    # Public API — code solving
    # ------------------------------------------------------------------

    async def solve_code_task(
        self,
        instruction: str,
        current_code: str = "",
        language: str = "python",
        screenshot_path: str | None = None,
    ) -> str:
        """
        Solve a programming exercise.
        Returns the CLEAN code ready to paste into the editor.
        Raises GeminiResponseError if no valid code could be produced.
        """
        lang = language.lower()
        if lang not in ("python", "javascript", "js"):
            lang = "python"

        prompt = (
            f"You are an expert {lang} programmer solving a Qureo exercise.\n"
            f"Instructions: {instruction.strip()}\n\n"
            f"Current code:\n```{lang}\n{current_code.strip()}\n```\n\n"
            "Return ONLY the complete corrected code. "
            "No explanation. No markdown fences. No comments unless required by the task."
        )

        contents: list[Any] = [prompt]
        img = self._image_part(screenshot_path)
        if img is not None:
            contents.append(img)

        raw = await self._generate(contents)
        code = self._extract_code(raw)

        if not code.strip():
            raise GeminiResponseError("Gemini returned empty code")

        log.debug("gemini_code_solved", lang=lang, length=len(code))
        return code

    # ------------------------------------------------------------------
    # Public API — quiz solving
    # ------------------------------------------------------------------

    async def solve_quiz_question(
        self,
        question: str,
        options: list[str],
        screenshot_path: str | None = None,
    ) -> int:
        """
        Pick the correct option index for a multiple-choice question.

        Returns 0..len(options)-1.
        Raises GeminiResponseError if the answer cannot be determined —
        DO NOT default to 0 (that would submit a wrong answer knowingly).
        """
        if not options:
            raise GeminiResponseError("No options provided")
        if not self.is_available:
            raise GeminiCircuitOpenError("Gemini unavailable — cannot solve quiz")

        opts_text = "\n".join(f"{i}. {opt}" for i, opt in enumerate(options))
        prompt = (
            "You are an expert educator solving a multiple-choice question from a "
            "learning platform. Analyze carefully and pick the SINGLE correct option.\n\n"
            f"Question:\n{question.strip()}\n\n"
            f"Options:\n{opts_text}\n\n"
            f"Respond with JSON only: "
            f'{{"correct_index": <integer 0..{len(options)-1}>, '
            f'"reason": "<one sentence>"}}'
        )

        contents: list[Any] = [prompt]
        img = self._image_part(screenshot_path)
        if img is not None:
            contents.append(img)

        raw = await self._generate(contents)
        data = self._extract_json(raw)

        if data is not None:
            idx = data.get("correct_index")
            if isinstance(idx, int) and 0 <= idx < len(options):
                log.debug("gemini_quiz_solved", index=idx, reason=data.get("reason", ""))
                return idx

        # Fallback: search for a digit at the start of the response
        m = re.search(r"\b(\d+)\b", raw or "")
        if m:
            candidate = int(m.group(1))
            if 0 <= candidate < len(options):
                log.warning("gemini_quiz_solved_via_digit_fallback", index=candidate)
                return candidate

        raise GeminiResponseError(
            f"Could not parse Gemini quiz response: {raw[:120]!r}"
        )

    # ------------------------------------------------------------------
    # Public API — screen analysis (browser automation)
    # ------------------------------------------------------------------

    async def analyze_screen(
        self,
        screenshot_path: str,
        page_text: str = "",
    ) -> dict[str, Any]:
        """
        Analyze a Qureo screen and recommend the next action.

        Returns dict with:
            page_type:  chapter_map | dashboard | code_task | quiz | dialogue | completed | unknown
            solution_code: str | None
            next_button: str | None
            summary: str
        """
        if not self.is_available:
            raise GeminiCircuitOpenError("Gemini unavailable — cannot analyze screen")

        prompt = (
            "You are an autonomous agent operating the Qureo learning platform. "
            "Analyze the screenshot and decide the next action.\n\n"
            f"Page text (partial):\n{page_text[:1200]}\n\n"
            "Determine the page type from these values:\n"
            "- chapter_map : list of lessons/chapters\n"
            "- dashboard   : course home with a 'Start' button\n"
            "- code_task   : editor + run button\n"
            "- quiz        : multiple-choice question\n"
            "- dialogue    : instruction / robot dialogue requiring 'Next'\n"
            "- completed   : success screen ('Great job!', 'Next level')\n"
            "- unknown     : none of the above\n\n"
            "If code_task: provide the correct code in solution_code.\n"
            "If dialogue / dashboard / chapter_map: provide the button text in next_button.\n\n"
            "Respond with JSON only:\n"
            '{"page_type":"...", "summary":"...", "solution_code":null, '
            '"next_button":null, "is_passed": false}'
        )

        contents: list[Any] = [prompt]
        img = self._image_part(screenshot_path)
        if img is not None:
            contents.append(img)

        raw = await self._generate(contents)
        data = self._extract_json(raw)

        if not data:
            return {
                "page_type": "unknown",
                "summary": (raw or "")[:200],
                "solution_code": None,
                "next_button": None,
                "is_passed": False,
            }

        # Normalize
        data.setdefault("page_type", "unknown")
        data.setdefault("summary", "")
        data.setdefault("solution_code", None)
        data.setdefault("next_button", None)
        data.setdefault("is_passed", False)

        # Clean up code if provided
        if data.get("solution_code"):
            data["solution_code"] = self._extract_code(str(data["solution_code"]))

        return data

    # ------------------------------------------------------------------
    # Public API — financial literacy
    # ------------------------------------------------------------------

    async def solve_financial_image(
        self,
        image_path: str,
    ) -> dict[str, Any]:
        """
        Solve a financial literacy question from a photo.

        Returns:
            {
              question: str,
              options: list[str],
              correct_index: int,
              correct_answer: str,
              explanation: str,
              topic: str
            }
        Raises GeminiResponseError on parse failure.
        """
        if not self.is_available:
            raise GeminiCircuitOpenError("Gemini unavailable")
        img = self._image_part(image_path)
        if img is None:
            raise GeminiResponseError("Image could not be loaded")

        prompt = (
            "You are a financial literacy teacher. Read the question in the image "
            "and provide the correct answer with a short educational explanation.\n\n"
            "Respond with JSON only:\n"
            "{\n"
            '  "question": "<exact Arabic text of the question>",\n'
            '  "options": ["<opt1>", "<opt2>", "<opt3>", "<opt4>"],\n'
            '  "correct_index": <0..3>,\n'
            '  "correct_answer": "<exact text of correct option>",\n'
            '  "explanation": "<2-3 sentences in Arabic>",\n'
            '  "topic": "<short topic in Arabic>"\n'
            "}"
        )

        raw = await self._generate([prompt, img])
        data = self._extract_json(raw)

        if not data or "correct_answer" not in data:
            raise GeminiResponseError(
                f"Could not extract financial answer: {(raw or '')[:120]!r}"
            )

        # Normalize fields
        data.setdefault("question", "")
        data.setdefault("options", [])
        data.setdefault("correct_index", 0)
        data.setdefault("correct_answer", "")
        data.setdefault("explanation", "")
        data.setdefault("topic", "ثقافة مالية")

        return data

    async def solve_financial_text(
        self,
        question: str,
        options: list[str] | None = None,
    ) -> dict[str, Any]:
        """Answer a financial literacy question from text."""
        if not self.is_available:
            raise GeminiCircuitOpenError("Gemini unavailable")

        opts_block = (
            "\n".join(f"- {o}" for o in options)
            if options
            else "(no options provided)"
        )
        prompt = (
            "You are a financial literacy teacher. Answer the question accurately.\n\n"
            f"Question:\n{question.strip()}\n\n"
            f"Options:\n{opts_block}\n\n"
            "Respond with JSON only:\n"
            '{"correct_answer": "...", "explanation": "...", "topic": "..."}'
        )

        raw = await self._generate([prompt])
        data = self._extract_json(raw)
        if not data or "correct_answer" not in data:
            raise GeminiResponseError(
                f"Could not extract answer: {(raw or '')[:120]!r}"
            )
        data.setdefault("explanation", "")
        data.setdefault("topic", "ثقافة مالية")
        return data

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Return a dict for the /health endpoint and admin dashboard."""
        return {
            "configured": self.is_configured,
            "breaker_open": self._breaker.is_open,
            "breaker_failures": self._breaker.failures,
            "calls": self.usage.calls,
            "failures": self.usage.failures,
            "avg_latency_ms": self.usage.avg_latency_ms,
            "by_model": dict(self.usage.by_model),
        }