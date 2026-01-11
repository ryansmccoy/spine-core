"""Request context middleware for tracing."""

import uuid
from contextvars import ContextVar
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from market_spine.observability.logging import get_logger

# Context variable to hold request ID throughout the request lifecycle
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

logger = get_logger(__name__)


def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_var.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to set up request context with correlation ID.

    This middleware:
    - Generates or extracts a request ID for each request
    - Stores it in a context variable for logging/tracing
    - Adds it to response headers for client correlation
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with context setup."""
        # Get request ID from header or generate new one
        request_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Correlation-ID")
            or str(uuid.uuid4())
        )

        # Set in context variable
        token = request_id_var.set(request_id)

        try:
            # Log request start
            logger.info(
                "request_started",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                client=request.client.host if request.client else "unknown",
            )

            response = await call_next(request)

            # Log request completion
            logger.info(
                "request_completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
            )

            # Add correlation headers to response
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            logger.exception(
                "request_failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                error=str(e),
            )
            raise

        finally:
            request_id_var.reset(token)
