"""Timing middleware — adds ``X-Process-Time-Ms`` header.

Manifesto:
    Server-side latency should be visible to every caller
    without extra instrumentation.  The timing header makes
    slow requests immediately obvious in browser dev-tools.

Tags:
    spine-core, api, middleware, timing, latency, observability

Doc-Types:
    api-reference
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class TimingMiddleware(BaseHTTPMiddleware):
    """Measure and expose request processing time in milliseconds."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
        return response
