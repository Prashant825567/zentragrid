"""In-process sliding-window rate limiter.

Intentionally simple and dependency-free. Buckets are keyed per
API key / owner and per operation class, with limits configurable via env.

NOTE: counters are per process. With multiple Render instances the effective
limit is ``limit x instances``. The interface is designed so a Redis backend
can be dropped in later without touching call sites.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Deque, Dict

from app.core.config import settings
from app.core.errors import RateLimitedError

WINDOW_SECONDS = 60


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int) -> None:
        """Raise :class:`RateLimitedError` when ``key`` exceeds ``limit``/minute."""
        if not settings.RATE_LIMIT_ENABLED or limit <= 0:
            return

        now = time.monotonic()
        cutoff = now - WINDOW_SECONDS

        async with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(int(bucket[0] + WINDOW_SECONDS - now) + 1, 1)
                raise RateLimitedError(
                    f"Rate limit of {limit} requests/minute exceeded.",
                    details={"retry_after": retry_after, "limit": limit},
                )

            bucket.append(now)

            # Opportunistic cleanup so idle buckets do not leak memory.
            if len(self._buckets) > 10_000:
                for stale_key in [k for k, v in self._buckets.items() if not v]:
                    self._buckets.pop(stale_key, None)

    def reset(self) -> None:
        self._buckets.clear()


limiter = SlidingWindowLimiter()


def limit_for(operation: str) -> int:
    return {
        "upload": settings.RATE_LIMIT_UPLOAD_PER_MIN,
        "download": settings.RATE_LIMIT_DOWNLOAD_PER_MIN,
        "stream": settings.RATE_LIMIT_STREAM_PER_MIN,
        "dashboard": settings.RATE_LIMIT_DASHBOARD_PER_MIN,
    }.get(operation, settings.RATE_LIMIT_GENERAL_PER_MIN)


async def enforce(scope: str, identity: str, operation: str) -> None:
    await limiter.check(f"{scope}:{identity}:{operation}", limit_for(operation))
