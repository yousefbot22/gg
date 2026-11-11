"""
Rate limiter with jitter — mimics human behavior to avoid Qureo detection.

Key features:
- Randomized delays (not fixed sleep)
- Exponential backoff on failures
- Per-endpoint buckets
- Retry with tenacity
"""
from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from src.config import settings
from src.core.logger import get_logger
from src.core.exceptions import RateLimitError

log = get_logger(__name__)

T = TypeVar("T")


@dataclass
class Bucket:
    """Token-bucket for a specific endpoint."""
    min_delay: float = settings.rate_limit_min_delay
    max_delay: float = settings.rate_limit_max_delay
    last_call: float = field(default_factory=time.monotonic)
    consecutive_failures: int = 0
    backoff_until: float = 0.0


class RateLimiter:
    """Per-endpoint adaptive rate limiter."""

    def __init__(self):
        self._buckets: dict[str, Bucket] = defaultdict(Bucket)

    async def acquire(self, endpoint: str) -> None:
        """Wait before hitting the endpoint."""
        bucket = self._buckets[endpoint]
        now = time.monotonic()

        # Honor backoff
        if now < bucket.backoff_until:
            wait = bucket.backoff_until - now
            log.debug("rate_limit_backoff", endpoint=endpoint, wait=round(wait, 2))
            await asyncio.sleep(wait)

        # Jittered delay since last call
        elapsed = now - bucket.last_call
        target_delay = random.uniform(bucket.min_delay, bucket.max_delay)
        if elapsed < target_delay:
            await asyncio.sleep(target_delay - elapsed)

        bucket.last_call = time.monotonic()

    def record_failure(self, endpoint: str) -> None:
        """Increase backoff after a failure."""
        bucket = self._buckets[endpoint]
        bucket.consecutive_failures += 1
        # Exponential backoff: 2s, 4s, 8s, ... (capped at 60s)
        backoff = min(2.0 ** bucket.consecutive_failures, 60.0)
        bucket.backoff_until = time.monotonic() + backoff
        log.warning(
            "rate_limit_failure",
            endpoint=endpoint,
            failures=bucket.consecutive_failures,
            backoff_sec=backoff,
        )

    def record_success(self, endpoint: str) -> None:
        """Reset on success."""
        bucket = self._buckets[endpoint]
        if bucket.consecutive_failures > 0:
            log.info("rate_limit_recovered", endpoint=endpoint)
        bucket.consecutive_failures = 0
        bucket.backoff_until = 0.0

    async def call(
        self,
        endpoint: str,
        func: Callable[[], "asyncio.Future[T]"],
        max_retries: int | None = None,
        retry_on: tuple[type[Exception], ...] = (Exception,),
    ) -> T:
        """Execute with rate limiting + retry."""
        retries = max_retries if max_retries is not None else settings.rate_limit_max_retries
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            await self.acquire(endpoint)
            try:
                result = await func()
                self.record_success(endpoint)
                return result
            except retry_on as e:
                last_error = e
                self.record_failure(endpoint)
                if attempt == retries:
                    break
                log.warning(
                    "call_retry",
                    endpoint=endpoint,
                    attempt=attempt + 1,
                    error=str(e),
                )

        raise RateLimitError(
            f"Failed after {retries + 1} attempts: {last_error}"
        ) from last_error


# Global limiter (one per process)
rate_limiter = RateLimiter()