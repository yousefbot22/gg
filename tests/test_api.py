"""API logic tests (no real network)."""
import pytest


@pytest.mark.asyncio
async def test_rate_limiter_delays():
    from src.core.rate_limiter import RateLimiter

    limiter = RateLimiter()
    limiter._buckets["ep"].min_delay = 0.05
    limiter._buckets["ep"].max_delay = 0.05

    import time
    start = time.monotonic()
    await limiter.acquire("ep")
    await limiter.acquire("ep")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.04


@pytest.mark.asyncio
async def test_rate_limiter_backoff():
    from src.core.rate_limiter import RateLimiter

    limiter = RateLimiter()
    limiter._buckets["ep"].min_delay = 0
    limiter._buckets["ep"].max_delay = 0

    async def fail():
        raise ValueError("boom")

    with pytest.raises(Exception):
        await limiter.call("ep", fail, max_retries=1)


def test_circuit_breaker_opens():
    from src.solver.gemini_solver import CircuitBreaker

    cb = CircuitBreaker(threshold=3, cooldown=100)
    assert not cb.is_open
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open
    cb.record_success()
    assert not cb.is_open


def test_gemini_extract_json():
    from src.solver.gemini_solver import GeminiSolver

    text = '```json\n{"correct_index": 2}\n```'
    data = GeminiSolver._extract_json(text)
    assert data == {"correct_index": 2}

    text2 = 'prefix {"correct_index": 1} suffix'
    assert GeminiSolver._extract_json(text2) == {"correct_index": 1}