"""Tiny in-memory sliding-window limiter. Valid because the backend runs as ONE process (see README)."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, max_calls: int, per_seconds: float, name: str):
        self.max_calls, self.per, self.name = max_calls, per_seconds, name
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.per:
            q.popleft()
        if len(q) >= self.max_calls:
            raise HTTPException(429, f"Too many {self.name} requests. Please wait and try again.")
        q.append(now)
        if len(self._hits) > 5000:           # keep memory bounded
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.per]:
                self._hits.pop(k, None)
