"""
Per-client rate-limiting middleware using a fixed-window counter.

When ``rate_limit_enabled=True``, each client IP is allowed at most
``rate_limit_rpm`` requests per 60-second window.  Excess requests
receive 429 with a ``Retry-After`` header.

Implementation uses an in-memory dict (no Redis required).  For
multi-process deployments, swap to Redis via the execution-layer
``TokenBucketLimiter`` or a shared store.

Manifesto:
    Rate-limiting protects the API from accidental or malicious
    overload.  The in-memory implementation works out of the box;
    production deployments can swap to Redis without code changes.

Tags:
    spine-core, api, middleware, rate-limiting, fixed-window, 429

Doc-Types:
    api-reference
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@dataclass
class _WindowCounter:
    """Fixed-window counter for a single client."""

    count: int = 0
    window_start: float = field(default_factory=time.monotonic)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-IP rate limiter.

    Parameters
    ----------
    app:
        The ASGI application to wrap.
    enabled:
        Master switch — when ``False`` all requests pass through.
    rpm:
        Maximum requests per minute per client IP.
    """

    def __init__(
        self,
        app: object,
        enabled: bool = False,
        rpm: int = 120,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._enabled = enabled
        self._rpm = rpm
        self._window_seconds = 60.0
        self._counters: dict[str, _WindowCounter] = defaultdict(_WindowCounter)

    def _client_ip(self, request: Request) -> str:
        """Extract client IP, respecting X-Forwarded-For behind a proxy."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._enabled:
            return await call_next(request)

        ip = self._client_ip(request)
        now = time.monotonic()
        counter = self._counters[ip]

        # Reset window if expired
        if now - counter.window_start >= self._window_seconds:
            counter.count = 0
            counter.window_start = now

        counter.count += 1

        if counter.count > self._rpm:
            retry_after = int(self._window_seconds - (now - counter.window_start)) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "title": "Too Many Requests",
                    "status": 429,
                    "detail": f"Rate limit exceeded ({self._rpm} req/min). Retry after {retry_after}s.",
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        # Expose rate-limit headers for client visibility
        remaining = max(0, self._rpm - counter.count)
        response.headers["X-RateLimit-Limit"] = str(self._rpm)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
