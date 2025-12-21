"""Request-ID middleware — injects ``X-Request-ID`` on every request.

Manifesto:
    Every request gets a unique ID so logs, traces, and error
    reports can be correlated across services.

Tags:
    spine-core, api, middleware, request-id, tracing, correlation

Doc-Types:
    api-reference
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request/response cycle."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
