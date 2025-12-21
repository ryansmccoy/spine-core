"""Health-check MCP tools."""

from __future__ import annotations

from typing import Any

from spine.mcp import _app

mcp = _app.mcp


@mcp.tool()
async def health_check() -> dict[str, Any]:
    """Check system health status.

    Returns:
        Health status including database connectivity
    """
    from spine.ops.context import OperationContext
    from spine.ops.database import check_database_health

    ctx = _app._get_context()
    if not ctx.initialized:
        return {
            "status": "unhealthy",
            "database": {"connected": False},
            "version": _app._get_version(),
        }

    result = check_database_health(OperationContext(conn=ctx.conn))

    if not result.success:
        return {
            "status": "unhealthy",
            "database": {"connected": False},
            "error": result.error_message,
            "version": _app._get_version(),
        }

    db = result.data
    return {
        "status": "healthy" if db.connected else "unhealthy",
        "database": {
            "connected": db.connected,
            "backend": db.backend,
            "table_count": db.table_count,
            "latency_ms": db.latency_ms,
        },
        "version": _app._get_version(),
    }


@mcp.tool()
async def get_capabilities() -> dict[str, Any]:
    """Get runtime capabilities of the spine-core system.

    Returns which features and backends are available in the
    current deployment (scheduling, DLQ, async execution, etc.).

    Returns:
        Dictionary of capability flags
    """
    from spine.ops.context import OperationContext
    from spine.ops.health import get_capabilities as _get_capabilities

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    result = _get_capabilities(OperationContext(conn=ctx.conn))

    if not result.success:
        return {"error": result.error_message}

    caps = result.data
    return {
        "tier": caps.tier,
        "sync_execution": caps.sync_execution,
        "async_execution": caps.async_execution,
        "scheduling": caps.scheduling,
        "rate_limiting": caps.rate_limiting,
        "execution_history": caps.execution_history,
        "dlq": caps.dlq,
    }
