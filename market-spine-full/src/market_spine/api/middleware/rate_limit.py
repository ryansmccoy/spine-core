"""Rate limiting middleware for API protection."""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from market_spine.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitState:
    """Tracks rate limit state for a client."""

    tokens: float = 10.0
    last_update: float = field(default_factory=time.monotonic)


class RateLimiter:
    """Token bucket rate limiter.

    Implements a token bucket algorithm where:
    - Each client gets a bucket with max_tokens capacity
    - Tokens refill at refill_rate per second
    - Each request consumes 1 token
    - Requests are rejected when bucket is empty
    """

    def __init__(
        self,
        max_tokens: float = 100.0,
        refill_rate: float = 10.0,  # tokens per second
    ):
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self._buckets: dict[str, RateLimitState] = defaultdict(RateLimitState)

    def _get_client_id(self, request: Request) -> str:
        """Extract client identifier from request."""
        # Use X-Forwarded-For if behind proxy, otherwise use client host
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _refill(self, state: RateLimitState) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - state.last_update
        state.tokens = min(
            self.max_tokens,
            state.tokens + elapsed * self.refill_rate,
        )
        state.last_update = now

    def allow_request(self, request: Request) -> tuple[bool, dict]:
        """Check if request should be allowed.

        Returns:
            Tuple of (allowed, rate_limit_headers).
        """
        client_id = self._get_client_id(request)
        state = self._buckets[client_id]

        self._refill(state)

        # Calculate reset time (avoid division by zero)
        reset_seconds = (
            (self.max_tokens - state.tokens) / self.refill_rate
            if self.refill_rate > 0
            else 3600  # Default to 1 hour if no refill
        )

        headers = {
            "X-RateLimit-Limit": str(int(self.max_tokens)),
            "X-RateLimit-Remaining": str(max(0, int(state.tokens - 1))),
            "X-RateLimit-Reset": str(int(time.time() + reset_seconds)),
        }

        if state.tokens >= 1:
            state.tokens -= 1
            return True, headers

        # Calculate retry-after (avoid division by zero)
        retry_after = (1 - state.tokens) / self.refill_rate if self.refill_rate > 0 else 3600
        headers["Retry-After"] = str(int(retry_after) + 1)

        logger.warning(
            "rate_limit_exceeded",
            client_id=client_id,
            tokens=state.tokens,
            retry_after=retry_after,
        )

        return False, headers


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""

    def __init__(
        self,
        app,
        max_tokens: float = 100.0,
        refill_rate: float = 10.0,
        exclude_paths: list[str] | None = None,
    ):
        super().__init__(app)
        self.limiter = RateLimiter(max_tokens, refill_rate)
        self.exclude_paths = exclude_paths or ["/health", "/metrics"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        # Skip rate limiting for excluded paths
        if any(request.url.path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        allowed, headers = self.limiter.allow_request(request)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please retry later."},
                headers=headers,
            )

        response = await call_next(request)

        # Add rate limit headers to response
        for key, value in headers.items():
            response.headers[key] = value

        return response
