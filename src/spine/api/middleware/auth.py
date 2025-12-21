"""
API-key authentication middleware.

When ``SPINE_API_KEY`` is set, every request must include a matching
``X-API-Key`` header (or ``?api_key=`` query param).  Unauthenticated
requests receive a 401 JSON response.

Bypass paths (no auth required):
  - ``/health/*``
  - ``/docs``, ``/redoc``, ``/openapi.json``
  - ``/metrics``

Manifesto:
    API-key authentication is the simplest secure default.
    Bypass paths let health-checks and OpenAPI docs work
    without credentials.

Tags:
    spine-core, api, middleware, authentication, API-key

Doc-Types:
    api-reference
"""

from __future__ import annotations

import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Paths that never require authentication
_BYPASS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^/health"),
    re.compile(r"^/metrics$"),
    re.compile(r"/docs$"),
    re.compile(r"/redoc$"),
    re.compile(r"/openapi\.json$"),
]


def _is_bypass(path: str) -> bool:
    """Return True if *path* should skip authentication."""
    return any(p.search(path) for p in _BYPASS_PATTERNS)


class AuthMiddleware(BaseHTTPMiddleware):
    """Reject requests that lack a valid API key.

    If ``api_key`` is ``None`` (the default), authentication is disabled
    and all requests pass through.

    Parameters
    ----------
    app:
        The ASGI application to wrap.
    api_key:
        The expected API key value.  ``None`` disables enforcement.
    """

    def __init__(self, app: object, api_key: str | None = None) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # No key configured → auth disabled
        if self._api_key is None:
            return await call_next(request)

        # Bypass certain well-known paths
        if _is_bypass(request.url.path):
            return await call_next(request)

        # Check header first, then query param
        provided = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if provided != self._api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "Missing or invalid API key. Provide X-API-Key header.",
                },
            )

        return await call_next(request)
