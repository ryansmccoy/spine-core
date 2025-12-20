"""
Common API schemas — shared envelopes and RFC 7807 errors.

Every endpoint returns either :class:`SuccessResponse` (200/201/202)
or :class:`ProblemDetail` (4xx/5xx).  Paged endpoints embed
:class:`PageMeta` alongside the item list.

Response Envelope Conventions:
    - All 2xx responses use ``SuccessResponse[T]`` or ``PagedResponse[T]``
    - All 4xx/5xx responses use ``ProblemDetail`` (RFC 7807)
    - ``elapsed_ms`` tracks server-side processing time
    - ``warnings`` contains non-fatal issues to display to users

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ── Links (HATEOAS-lite) ────────────────────────────────────────────────


class Link(BaseModel):
    """Hypermedia link for resource navigation.

    UI Hints:
        Use ``rel`` to identify link purpose (e.g., 'self', 'next', 'parent').
        Render as clickable navigation when appropriate.
    """

    rel: str = Field(description="Link relation (e.g., 'self', 'next', 'prev', 'parent')")
    href: str = Field(description="Target URL")
    method: str = Field(default="GET", description="HTTP method for this link")


# ── RFC 7807 Problem Detail ─────────────────────────────────────────────


class ErrorDetail(BaseModel):
    """Structured error detail for field-level or nested errors.

    UI Hints:
        Display field errors next to corresponding form inputs.
        Use ``code`` for programmatic error handling.
    """

    code: str = Field(description="Machine-readable error code (e.g., 'REQUIRED', 'INVALID_FORMAT')")
    message: str = Field(description="Human-readable error description")
    field: str | None = Field(default=None, description="Field path if error is field-specific")


class ProblemDetail(BaseModel):
    """RFC 7807 «Problem Details for HTTP APIs».

    Used as the canonical error envelope for all non-2xx responses.
    Frontends should parse this structure for error display.

    UI Hints:
        Display ``title`` as error heading, ``detail`` as explanation.
        Show ``errors`` list for form validation feedback.
        Use ``status`` for HTTP status code styling.

    Error Codes:
        - ``NOT_FOUND`` (404): Resource does not exist
        - ``VALIDATION_FAILED`` (400): Invalid input data
        - ``CONFLICT`` (409): Operation conflicts with current state
        - ``NOT_CANCELLABLE`` (409): Run cannot be cancelled
        - ``ALREADY_COMPLETE`` (409): Run has already finished
        - ``LOCKED`` (423): Resource is locked
        - ``QUOTA_EXCEEDED`` (429): Rate/quota limit reached
        - ``RATE_LIMITED`` (429): Too many requests
        - ``TRANSIENT`` (503): Temporary failure, retry later
        - ``UNAVAILABLE`` (503): Service unavailable
        - ``INTERNAL`` (500): Unexpected server error

    Example:
        {
            "type": "about:blank",
            "title": "Run not found",
            "status": 404,
            "detail": "Run 'abc-123' does not exist",
            "instance": "/api/v1/runs/abc-123",
            "errors": []
        }
    """

    type: str = Field(default="about:blank", description="Error type URI (usually 'about:blank')")
    title: str = Field(description="Short human-readable error summary")
    status: int = Field(description="HTTP status code (e.g., 400, 404, 500)")
    detail: str = Field(default="", description="Human-readable explanation of the error")
    instance: str = Field(default="", description="URI of the failing request")
    errors: list[ErrorDetail] = Field(
        default_factory=list,
        description="List of field-level or nested error details",
    )


# ── Success Envelopes ────────────────────────────────────────────────────


class PageMeta(BaseModel):
    """Pagination metadata for list responses.

    UI Hints:
        Display page controls based on ``has_more``.
        Show "N of M" using ``total``.
        Calculate page number from ``offset / limit``.
    """

    total: int = Field(description="Total items across all pages")
    limit: int = Field(description="Items per page (requested)")
    offset: int = Field(description="Current offset (0-based)")
    has_more: bool = Field(description="True if more pages exist after current")

    # Extended pagination fields
    page: int = Field(default=1, description="Current page number (1-indexed)")
    total_pages: int = Field(default=1, description="Total number of pages")
    has_prev: bool = Field(default=False, description="True if previous page exists")

    @classmethod
    def from_result(
        cls,
        total: int,
        limit: int,
        offset: int,
        *,
        page: int | None = None,
    ) -> PageMeta:
        """Factory that auto-computes derived fields."""
        total_pages = max(1, (total + limit - 1) // limit)
        current_page = page if page is not None else (offset // limit) + 1
        return cls(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
            page=current_page,
            total_pages=total_pages,
            has_prev=current_page > 1,
        )


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success envelope for single-item responses.

    All 2xx responses (except paged lists) use this envelope.

    UI Hints:
        Extract ``data`` for display content.
        Show ``warnings`` as toast notifications if present.
        Use ``elapsed_ms`` for performance monitoring.
    """

    data: T = Field(description="Response payload (type varies by endpoint)")
    elapsed_ms: float = Field(default=0.0, description="Server-side processing time in milliseconds")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings to display to users",
    )
    links: list[Link] = Field(
        default_factory=list,
        description="HATEOAS navigation links",
    )


class PagedResponse(BaseModel, Generic[T]):
    """Paged success envelope for list responses.

    Used for all paginated list endpoints.

    UI Hints:
        Render ``data`` in a table or list view.
        Use ``page`` for pagination controls.
        Show ``warnings`` as toast notifications if present.
    """

    data: list[T] = Field(description="List of items for this page")
    page: PageMeta = Field(description="Pagination metadata")
    elapsed_ms: float = Field(default=0.0, description="Server-side processing time in milliseconds")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings to display to users",
    )
    links: list[Link] = Field(
        default_factory=list,
        description="HATEOAS navigation links (next, prev, etc.)",
    )
