from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from typing import Optional

from fastapi import HTTPException

from bank_api.config import Settings


def require_admin_key(settings: Settings, x_admin_key: Optional[str] = None) -> None:
    if not x_admin_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key header")


class RateLimiter:
    """Simple in-memory sliding window rate limiter per client IP."""

    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            window_start = now - self.window_seconds
            hits = [t for t in self._hits[key] if t >= window_start]
            if len(hits) >= self.max_requests:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True

    def retry_after(self, key: str) -> int:
        with self._lock:
            if not self._hits[key]:
                return self.window_seconds
            oldest = min(self._hits[key])
            return max(1, int(self.window_seconds - (time.time() - oldest)))
