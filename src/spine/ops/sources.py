"""
Source operations.

CRUD for data sources, fetch history, cache entries, and database connections.
Wires ``core_sources``, ``core_source_fetches``, ``core_source_cache``,
and ``core_database_connections`` tables to the API/CLI.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from spine.core.logging import get_logger
from spine.core.repositories import SourceRepository
from spine.ops.context import OperationContext
from spine.ops.requests import (
    CreateDatabaseConnectionRequest,
    CreateSourceRequest,
    ListDatabaseConnectionsRequest,
    ListSourceFetchesRequest,
    ListSourcesRequest,
)
from spine.ops.responses import (
    DatabaseConnectionSummary,
    SourceCacheSummary,
    SourceDetail,
    SourceFetchSummary,
    SourceSummary,
)
from spine.ops.result import OperationResult, PagedResult, start_timer

logger = get_logger(__name__)


def _source_repo(ctx: OperationContext) -> SourceRepository:
    return SourceRepository(ctx.conn)


# ------------------------------------------------------------------ #
# Sources
# ------------------------------------------------------------------ #


def list_sources(
    ctx: OperationContext,
    request: ListSourcesRequest,
) -> PagedResult[SourceSummary]:
    """List registered data sources with optional filtering."""
    timer = start_timer()

    try:
        repo = _source_repo(ctx)
        rows, total = repo.list_sources(
            source_type=request.source_type,
            domain=request.domain,
            enabled=request.enabled,
            limit=request.limit,
            offset=request.offset,
        )

        summaries = [_row_to_source_summary(r) for r in rows]
        return PagedResult.from_items(
            summaries,
            total=total,
            limit=request.limit,
            offset=request.offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to list sources: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


def get_source(
    ctx: OperationContext,
    source_id: str,
) -> OperationResult[SourceDetail]:
    """Get a single source by ID."""
    timer = start_timer()

    try:
        repo = _source_repo(ctx)
        row = repo.get_source(source_id)

        if not row:
            return OperationResult.fail(
                "NOT_FOUND",
                f"Source '{source_id}' not found",
                elapsed_ms=timer.elapsed_ms,
            )

        detail = _row_to_source_detail(row)
        return OperationResult.ok(detail, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to get source: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def register_source(
    ctx: OperationContext,
    request: CreateSourceRequest,
) -> OperationResult[dict]:
    """Register a new data source."""
    timer = start_timer()

    if ctx.dry_run:
        return OperationResult.ok(
            {"dry_run": True, "would_create": request.name},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        import json

        source_id = f"src_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()

        repo = _source_repo(ctx)
        repo.create_source({
            "id": source_id,
            "name": request.name,
            "source_type": request.source_type,
            "config_json": json.dumps(request.config),
            "domain": request.domain,
            "enabled": 1 if request.enabled else 0,
            "created_at": now,
            "updated_at": now,
        })
        ctx.conn.commit()

        return OperationResult.ok(
            {"id": source_id, "name": request.name, "created": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to register source: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def delete_source(
    ctx: OperationContext,
    source_id: str,
    dry_run: bool = False,
) -> OperationResult[dict]:
    """Delete a data source."""
    timer = start_timer()

    if dry_run or ctx.dry_run:
        return OperationResult.ok(
            {"dry_run": True, "would_delete": source_id},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        repo = _source_repo(ctx)
        repo.delete_source(source_id)
        ctx.conn.commit()

        return OperationResult.ok(
            {"id": source_id, "deleted": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to delete source: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def enable_source(
    ctx: OperationContext,
    source_id: str,
) -> OperationResult[dict]:
    """Enable a data source."""
    timer = start_timer()

    if ctx.dry_run:
        return OperationResult.ok(
            {"dry_run": True, "would_enable": source_id},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        now = datetime.utcnow().isoformat()
        repo = _source_repo(ctx)
        repo.set_enabled(source_id, True, now)
        ctx.conn.commit()

        return OperationResult.ok(
            {"id": source_id, "enabled": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to enable source: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def disable_source(
    ctx: OperationContext,
    source_id: str,
) -> OperationResult[dict]:
    """Disable a data source."""
    timer = start_timer()

    if ctx.dry_run:
        return OperationResult.ok(
            {"dry_run": True, "would_disable": source_id},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        now = datetime.utcnow().isoformat()
        repo = _source_repo(ctx)
        repo.set_enabled(source_id, False, now)
        ctx.conn.commit()

        return OperationResult.ok(
            {"id": source_id, "disabled": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to disable source: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Source Fetches
# ------------------------------------------------------------------ #


def list_source_fetches(
    ctx: OperationContext,
    request: ListSourceFetchesRequest,
) -> PagedResult[SourceFetchSummary]:
    """List source fetch history with optional filtering."""
    timer = start_timer()

    try:
        repo = _source_repo(ctx)
        since_str = request.since.isoformat() if request.since else None
        rows, total = repo.list_fetches(
            source_id=request.source_id,
            source_name=request.source_name,
            status=request.status,
            since=since_str,
            limit=request.limit,
            offset=request.offset,
        )

        summaries = [_row_to_fetch_summary(r) for r in rows]
        return PagedResult.from_items(
            summaries,
            total=total,
            limit=request.limit,
            offset=request.offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to list source fetches: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Source Cache
# ------------------------------------------------------------------ #


def list_source_cache(
    ctx: OperationContext,
    source_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PagedResult[SourceCacheSummary]:
    """List source cache entries."""
    timer = start_timer()

    try:
        repo = _source_repo(ctx)
        rows, total = repo.list_cache(
            source_id=source_id,
            limit=limit,
            offset=offset,
        )

        summaries = [_row_to_cache_summary(r) for r in rows]
        return PagedResult.from_items(
            summaries,
            total=total,
            limit=limit,
            offset=offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to list source cache: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


def invalidate_source_cache(
    ctx: OperationContext,
    source_id: str,
    dry_run: bool = False,
) -> OperationResult[dict]:
    """Invalidate all cache entries for a source."""
    timer = start_timer()

    if dry_run or ctx.dry_run:
        # Count entries that would be deleted
        repo = _source_repo(ctx)
        rows, count = repo.list_cache(source_id=source_id, limit=1)
        # Use total from list_cache for the count
        _, total_count = repo.list_cache(source_id=source_id, limit=0)
        return OperationResult.ok(
            {"dry_run": True, "would_delete": total_count, "source_id": source_id},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        repo = _source_repo(ctx)
        deleted = repo.invalidate_cache(source_id)
        ctx.conn.commit()

        return OperationResult.ok(
            {"source_id": source_id, "deleted": deleted, "invalidated": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to invalidate source cache: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Database Connections
# ------------------------------------------------------------------ #


def list_database_connections(
    ctx: OperationContext,
    request: ListDatabaseConnectionsRequest,
) -> PagedResult[DatabaseConnectionSummary]:
    """List registered database connections."""
    timer = start_timer()

    try:
        repo = _source_repo(ctx)
        rows, total = repo.list_db_connections(
            dialect=request.dialect,
            enabled=request.enabled,
            limit=request.limit,
            offset=request.offset,
        )

        summaries = [_row_to_db_conn_summary(r) for r in rows]
        return PagedResult.from_items(
            summaries,
            total=total,
            limit=request.limit,
            offset=request.offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to list database connections: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


def register_database_connection(
    ctx: OperationContext,
    request: CreateDatabaseConnectionRequest,
) -> OperationResult[dict]:
    """Register a new database connection."""
    timer = start_timer()

    if ctx.dry_run:
        return OperationResult.ok(
            {"dry_run": True, "would_create": request.name},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        conn_id = f"db_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()

        repo = _source_repo(ctx)
        repo.create_db_connection({
            "id": conn_id,
            "name": request.name,
            "dialect": request.dialect,
            "host": request.host,
            "port": request.port,
            "database": request.database,
            "username": request.username,
            "password_ref": request.password_ref,
            "pool_size": request.pool_size,
            "max_overflow": request.max_overflow,
            "pool_timeout": request.pool_timeout,
            "enabled": 1 if request.enabled else 0,
            "created_at": now,
            "updated_at": now,
        })
        ctx.conn.commit()

        return OperationResult.ok(
            {"id": conn_id, "name": request.name, "created": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to register database connection: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def delete_database_connection(
    ctx: OperationContext,
    connection_id: str,
    dry_run: bool = False,
) -> OperationResult[dict]:
    """Delete a database connection."""
    timer = start_timer()

    if dry_run or ctx.dry_run:
        return OperationResult.ok(
            {"dry_run": True, "would_delete": connection_id},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        repo = _source_repo(ctx)
        repo.delete_db_connection(connection_id)
        ctx.conn.commit()

        return OperationResult.ok(
            {"id": connection_id, "deleted": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to delete database connection: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def test_database_connection(
    ctx: OperationContext,
    connection_id: str,
) -> OperationResult[dict]:
    """Test a database connection."""
    timer = start_timer()

    try:
        # Get the connection config
        repo = _source_repo(ctx)
        row = repo.get_db_connection(connection_id)

        if not row:
            return OperationResult.fail(
                "NOT_FOUND",
                f"Database connection '{connection_id}' not found",
                elapsed_ms=timer.elapsed_ms,
            )

        # For now, just mark that we would test
        # Actual testing would require connecting to the target database
        return OperationResult.ok(
            {
                "id": connection_id,
                "test_status": "not_implemented",
                "message": "Connection testing not yet implemented",
            },
            elapsed_ms=timer.elapsed_ms,
            warnings=["Connection testing requires sqlalchemy to be configured"],
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to test database connection: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _row_to_source_summary(row: Any) -> SourceSummary:
    if isinstance(row, dict):
        d = row
    elif hasattr(row, "keys"):
        d = dict(row)
    else:
        d = {
            "id": row[0],
            "name": row[1],
            "source_type": row[2],
            "domain": row[4],
            "enabled": row[5],
            "created_at": row[6],
        }

    return SourceSummary(
        id=d.get("id", ""),
        name=d.get("name", ""),
        source_type=d.get("source_type", ""),
        domain=d.get("domain"),
        enabled=bool(d.get("enabled", 1)),
        created_at=d.get("created_at"),
    )


def _row_to_source_detail(row: Any) -> SourceDetail:
    import json

    if isinstance(row, dict):
        d = row
    elif hasattr(row, "keys"):
        d = dict(row)
    else:
        d = {
            "id": row[0],
            "name": row[1],
            "source_type": row[2],
            "config_json": row[3],
            "domain": row[4],
            "enabled": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }

    config = d.get("config_json", {})
    if isinstance(config, str):
        config = json.loads(config)

    return SourceDetail(
        id=d.get("id", ""),
        name=d.get("name", ""),
        source_type=d.get("source_type", ""),
        config=config,
        domain=d.get("domain"),
        enabled=bool(d.get("enabled", 1)),
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
    )


def _row_to_fetch_summary(row: Any) -> SourceFetchSummary:
    if isinstance(row, dict):
        d = row
    elif hasattr(row, "keys"):
        d = dict(row)
    else:
        d = {
            "id": row[0],
            "source_id": row[1],
            "source_name": row[2],
            "source_type": row[3],
            "source_locator": row[4],
            "status": row[5],
            "record_count": row[6],
            "byte_count": row[7],
            "started_at": row[11],
            "duration_ms": row[13],
            "error": row[14],
        }

    return SourceFetchSummary(
        id=d.get("id", ""),
        source_id=d.get("source_id"),
        source_name=d.get("source_name", ""),
        source_type=d.get("source_type", ""),
        source_locator=d.get("source_locator", ""),
        status=d.get("status", ""),
        record_count=d.get("record_count"),
        byte_count=d.get("byte_count"),
        started_at=d.get("started_at"),
        duration_ms=d.get("duration_ms"),
        error=d.get("error"),
    )


def _row_to_cache_summary(row: Any) -> SourceCacheSummary:
    if isinstance(row, dict):
        d = row
    elif hasattr(row, "keys"):
        d = dict(row)
    else:
        d = {
            "cache_key": row[0],
            "source_id": row[1],
            "source_type": row[2],
            "source_locator": row[3],
            "content_hash": row[4],
            "content_size": row[5],
            "fetched_at": row[7],
            "expires_at": row[8],
        }

    return SourceCacheSummary(
        cache_key=d.get("cache_key", ""),
        source_id=d.get("source_id"),
        source_type=d.get("source_type", ""),
        source_locator=d.get("source_locator", ""),
        content_hash=d.get("content_hash", ""),
        content_size=d.get("content_size", 0),
        fetched_at=d.get("fetched_at"),
        expires_at=d.get("expires_at"),
    )


def _row_to_db_conn_summary(row: Any) -> DatabaseConnectionSummary:
    if isinstance(row, dict):
        d = row
    elif hasattr(row, "keys"):
        d = dict(row)
    else:
        d = {
            "id": row[0],
            "name": row[1],
            "dialect": row[2],
            "host": row[3],
            "port": row[4],
            "database": row[5],
            "enabled": row[11],
            "last_connected_at": row[12],
            "last_error": row[13],
            "created_at": row[15],
        }

    return DatabaseConnectionSummary(
        id=d.get("id", ""),
        name=d.get("name", ""),
        dialect=d.get("dialect", ""),
        host=d.get("host"),
        port=d.get("port"),
        database=d.get("database", ""),
        enabled=bool(d.get("enabled", 1)),
        last_connected_at=d.get("last_connected_at"),
        last_error=d.get("last_error"),
        created_at=d.get("created_at"),
    )


def _err(code: str, message: str):
    from spine.ops.result import OperationError
    return OperationError(code=code, message=message)
