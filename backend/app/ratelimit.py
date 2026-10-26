"""Per-client fixed-window rate limiting, in process memory.

Good enough for a single-worker deploy (which the in-memory GameStore already
requires). Clients are keyed by IP; behind a reverse proxy, uvicorn must be
told to trust X-Forwarded-For (FORWARDED_ALLOW_IPS) or every player shares
the proxy's address.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        # client -> (window start, hits in window)
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, client: str) -> bool:
        if self.limit <= 0:  # 0 disables the limit
            return True
        with self._lock:
            now = self._clock()
            start, count = self._hits.get(client, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            if count >= self.limit:
                return False
            self._hits[client] = (start, count + 1)
            if len(self._hits) > 10_000:
                self._hits = {
                    k: v for k, v in self._hits.items() if now - v[0] < self.window
                }
            return True

    def __call__(self, request: Request) -> None:
        """FastAPI dependency: 429 when the client is over its limit."""
        client = request.client.host if request.client else "unknown"
        if not self.allow(client):
            raise HTTPException(
                status_code=429,
                detail="too many requests, slow down",
                headers={"Retry-After": str(int(self.window))},
            )
