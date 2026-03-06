"""
Recall v7.0 - Token-Bucket Rate Limiter Middleware

Per-IP rate limiting using a token bucket algorithm.
- ``RECALL_RATE_LIMIT_RPM`` env var: max requests per minute (default 0 = disabled).
- Returns 429 Too Many Requests with ``Retry-After`` header when exceeded.
"""
from __future__ import annotations

import os
import time
import threading
from typing import Dict, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response


class _TokenBucket:
    """Simple thread-safe token-bucket for one IP address."""

    __slots__ = ("capacity", "tokens", "refill_rate", "last_refill")

    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        """Try to consume one token.  Returns *True* if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    @property
    def retry_after(self) -> float:
        """Seconds until one full token is available."""
        if self.tokens >= 1.0:
            return 0.0
        return (1.0 - self.tokens) / self.refill_rate


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP token-bucket rate limiter.

    Reads ``RECALL_RATE_LIMIT_RPM`` (requests per minute) on first request.
    Set to ``0`` or leave unset to disable.
    """

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self._buckets: Dict[str, _TokenBucket] = {}
        self._lock = threading.Lock()
        self._limit: int | None = None  # lazily read
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = 300.0  # purge stale buckets every 5 min

    def _get_limit(self) -> int:
        """Read limit lazily so env can be set after import."""
        if self._limit is None:
            # v7.0.12: 修复 — 默认值改为 60 与 RecallConfig.recall_rate_limit_rpm 一致
            raw = os.environ.get("RECALL_RATE_LIMIT_RPM", os.environ.get("RECALL_RATE_LIMIT", "60"))
            try:
                self._limit = int(raw)
            except ValueError:
                self._limit = 60
        return self._limit

    def _get_bucket(self, ip: str, rpm: int) -> _TokenBucket:
        with self._lock:
            # Periodic cleanup of stale entries
            now = time.monotonic()
            if now - self._last_cleanup > self._cleanup_interval:
                self._last_cleanup = now
                stale = [k for k, b in self._buckets.items() if now - b.last_refill > 600]
                for k in stale:
                    del self._buckets[k]

            bucket = self._buckets.get(ip)
            if bucket is None:
                capacity = float(rpm)
                refill_rate = rpm / 60.0  # tokens per second
                bucket = _TokenBucket(capacity, refill_rate)
                self._buckets[ip] = bucket
            return bucket

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rpm = self._get_limit()
        if rpm <= 0:
            return await call_next(request)

        ip = self._client_ip(request)
        bucket = self._get_bucket(ip, rpm)

        if bucket.consume():
            return await call_next(request)

        retry = max(1, int(bucket.retry_after) + 1)
        return JSONResponse(
            status_code=429,
            content={
                "detail": f"请求过于频繁，请在 {retry} 秒后重试",
                "retry_after": retry,
            },
            headers={"Retry-After": str(retry)},
        )
