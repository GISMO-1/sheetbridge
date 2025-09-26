"""Simple in-memory token bucket rate limiter keyed by string."""

from __future__ import annotations

import time
from collections import defaultdict


class Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, capacity: int) -> None:
        self.tokens = float(capacity)
        self.updated = time.time()


_buckets: defaultdict[str, Bucket | None] = defaultdict(lambda: None)


def allow(key: str, rps: float, burst: int) -> bool:
    """Return True when the caller can proceed under the rate limit."""

    now = time.time()
    bucket = _buckets.get(key)
    if bucket is None:
        bucket = Bucket(burst)
        _buckets[key] = bucket
    elapsed = now - bucket.updated
    bucket.tokens = min(float(burst), bucket.tokens + elapsed * max(rps, 0.0))
    bucket.updated = now
    if bucket.tokens >= 1.0:
        bucket.tokens -= 1.0
        return True
    return False
