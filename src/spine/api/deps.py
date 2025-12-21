"""
FastAPI dependency injection — shared singletons and per-request factories.

Usage in routers::

    from spine.api.deps import OpContext, Settings

    @router.get("/things")
    def list_things(ctx: OpContext, settings: Settings):
        ...

Manifesto:
    Dependency injection keeps routers thin.  Singletons (settings,
    DB connection) are created once; per-request objects (OpContext)
    carry request-scoped state through the call chain.

Tags:
    spine-core, api, dependency-injection, singletons, OpContext

Doc-Types:
    api-reference
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Query, Request

from spine.api.settings import SpineCoreAPISettings
from spine.core.connection import create_connection
from spine.ops.context import OperationContext

# ── Settings (singleton) ─────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_settings() -> SpineCoreAPISettings:
    """Cached settings — loaded once per process."""
    return SpineCoreAPISettings()


# ── Database connection (per-request) ────────────────────────────────────


def get_connection(
    settings: Annotated[SpineCoreAPISettings, Depends(get_settings)],
) -> Generator[Any, None, None]:
    """Yield a database connection for the request lifespan.

    Supports SQLite (direct), PostgreSQL/TimescaleDB (via SQLAlchemy ORM
    bridge), and falls back to SQLite for unrecognised URLs.
    """
    conn, _info = create_connection(
        settings.database_url,
        data_dir=settings.data_dir,
    )

    try:
        yield conn
    finally:
        if hasattr(conn, "close"):
            conn.close()


# ── Operation context (per-request) ──────────────────────────────────────


def get_operation_context(
    request: Request,
    conn: Annotated[Any, Depends(get_connection)],
) -> OperationContext:
    """Build an :class:`OperationContext` from the current request."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return OperationContext(
        conn=conn,
        request_id=request_id,
        caller="api",
    )


# ── Pagination parameters (per-request) ─────────────────────────────────


@dataclass(frozen=True, slots=True)
class PaginationParams:
    """Pagination parameters for list endpoints.

    Attributes:
        page: Page number (1-indexed, converted to offset internally)
        page_size: Items per page (capped at 1000)
        sort_by: Optional column to sort by
        sort_order: Sort direction ('asc' or 'desc')
    """

    page: int = 1
    page_size: int = 50
    sort_by: str | None = None
    sort_order: str = "desc"

    @property
    def offset(self) -> int:
        """Calculate offset from page number."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Alias for page_size for compatibility."""
        return self.page_size


def get_pagination(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page (max 1000)"),
    sort_by: str | None = Query(None, description="Column to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort direction"),
) -> PaginationParams:
    """FastAPI dependency for pagination parameters.

    Usage::

        @router.get("/items")
        def list_items(pagination: Pagination):
            offset = pagination.offset
            limit = pagination.limit
            ...
    """
    return PaginationParams(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# ── Convenience type aliases ─────────────────────────────────────────────

Settings = Annotated[SpineCoreAPISettings, Depends(get_settings)]
Conn = Annotated[Any, Depends(get_connection)]
OpContext = Annotated[OperationContext, Depends(get_operation_context)]
Pagination = Annotated[PaginationParams, Depends(get_pagination)]
