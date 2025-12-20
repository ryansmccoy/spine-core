"""
Error-handling middleware — maps ops-layer errors to RFC 7807 responses.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from spine.api.schemas.common import ProblemDetail

# ── Error code → HTTP status mapping ─────────────────────────────────────

ERROR_CODE_TO_STATUS: dict[str, int] = {
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "VALIDATION_FAILED": 400,
    "INVALID_INPUT": 400,
    "NOT_CANCELLABLE": 409,
    "ALREADY_COMPLETE": 409,
    "LOCKED": 423,
    "QUOTA_EXCEEDED": 429,
    "RATE_LIMITED": 429,
    "TRANSIENT": 503,
    "UNAVAILABLE": 503,
    "INTERNAL": 500,
}


def status_for_error_code(code: str) -> int:
    """Resolve an ops error code to HTTP status, defaulting to 500."""
    return ERROR_CODE_TO_STATUS.get(code, 500)


def problem_response(
    *,
    status: int,
    title: str,
    detail: str = "",
    instance: str = "",
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """Build a RFC 7807 JSON error response."""
    body = ProblemDetail(
        title=title,
        status=status,
        detail=detail,
        instance=instance,
    )
    if errors:
        from spine.api.schemas.common import ErrorDetail
        body.errors = [ErrorDetail(**e) for e in errors]
    return JSONResponse(status_code=status, content=body.model_dump())


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — returns 500 with ProblemDetail."""
    return problem_response(
        status=500,
        title="Internal Server Error",
        detail=str(exc) if request.app.state.settings.debug else "An unexpected error occurred.",
        instance=str(request.url),
    )
