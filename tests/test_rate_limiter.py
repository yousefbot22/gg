import asyncio
import pytest
from src.core.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_delays():
    limiter = RateLimiter()
    limiter._buckets["ep1"].min_delay = 0.1
    limiter._buckets["ep1"].max_delay = 0.1
    start = asyncio.get_event_loop().time()
    await limiter.acquire("ep1")
    await limiter.acquire("ep1")
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed >= 0.1