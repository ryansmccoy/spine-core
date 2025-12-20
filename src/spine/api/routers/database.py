"""
Database router — init, purge, health, table counts.

POST /database/init
POST /database/purge
GET  /database/health
GET  /database/tables
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from spine.api.deps import OpContext
from spine.api.schemas.common import SuccessResponse
from spine.api.schemas.domains import (
    DatabaseHealthSchema,
    DatabaseInitSchema,
    PurgeResultSchema,
    TableCountSchema,
)
from spine.api.utils import _dc, _handle_error

router = APIRouter(prefix="/database")


@router.post("/init", response_model=SuccessResponse[DatabaseInitSchema])
def init_database(ctx: OpContext, dry_run: bool = Query(False)):
    """Initialise database schema (create tables)."""
    from spine.ops.database import initialize_database
    from spine.ops.requests import DatabaseInitRequest

    ctx.dry_run = dry_run
    request = DatabaseInitRequest()
    result = initialize_database(ctx, request)
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=DatabaseInitSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.post("/purge", response_model=SuccessResponse[PurgeResultSchema])
def purge_data(
    ctx: OpContext,
    older_than_days: int = Query(90, ge=1, description="Delete data older than N days"),
    dry_run: bool = Query(False, description="Preview only, do not delete"),
):
    """Purge old execution data.

    Removes execution records older than the specified threshold.
    Use for data retention compliance and storage management.

    Args:
        ctx: Operation context with database connection.
        older_than_days: Delete records older than this many days (default 90).
        dry_run: If True, returns what would be deleted without making changes.

    Returns:
        SuccessResponse containing PurgeResultSchema with deletion counts.

    Example:
        POST /api/v1/database/purge?older_than_days=30&dry_run=true

        Response:
        {
            "data": {
                "rows_deleted": 1500,
                "tables_purged": ["core_executions", "core_events"],
                "dry_run": true
            }
        }
    """
    from spine.ops.database import purge_old_data
    from spine.ops.requests import PurgeRequest

    ctx.dry_run = dry_run
    request = PurgeRequest(older_than_days=older_than_days)
    result = purge_old_data(ctx, request)
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=PurgeResultSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.get("/health", response_model=SuccessResponse[DatabaseHealthSchema])
def database_health(ctx: OpContext):
    """Check database connectivity and stats.

    Returns connection status, backend type, and latency metrics.
    Use for health dashboards and monitoring alerts.

    Args:
        ctx: Operation context with database connection.

    Returns:
        SuccessResponse containing DatabaseHealthSchema.

    Example:
        GET /api/v1/database/health

        Response:
        {
            "data": {
                "connected": true,
                "backend": "postgresql",
                "table_count": 8,
                "latency_ms": 2.5
            }
        }
    """
    from spine.ops.database import check_database_health

    result = check_database_health(ctx)
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=DatabaseHealthSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.get("/tables", response_model=SuccessResponse[list[TableCountSchema]])
def table_counts(ctx: OpContext):
    """Get row counts for all managed tables.

    Returns current row counts for each spine-core database table.
    Useful for capacity planning and monitoring data growth.

    Args:
        ctx: Operation context with database connection.

    Returns:
        SuccessResponse containing list of TableCountSchema items.

    Example:
        GET /api/v1/database/tables

        Response:
        {
            "data": [
                {"table": "core_executions", "count": 15420},
                {"table": "core_events", "count": 89650},
                {"table": "core_schedules", "count": 12}
            ]
        }
    """
    from spine.ops.database import get_table_counts

    result = get_table_counts(ctx)
    if not result.success:
        return _handle_error(result)
    items = [TableCountSchema(**_dc(tc)) for tc in (result.data or [])]
    return SuccessResponse(
        data=items,
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )
