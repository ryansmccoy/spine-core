"""Data source management MCP tools."""

from __future__ import annotations

from typing import Any

from spine.mcp import _app

mcp = _app.mcp


@mcp.tool()
async def list_sources(
    source_type: str | None = None,
    domain: str | None = None,
    enabled: bool | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List registered data sources.

    Args:
        source_type: Filter by type (file, http, database, s3, sftp)
        domain: Filter by domain
        enabled: Filter by enabled status
        limit: Maximum sources to return

    Returns:
        Dictionary with 'sources' list and 'total' count
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import ListSourcesRequest
    from spine.ops.sources import list_sources as _list_sources

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "sources": [], "total": 0}

    request = ListSourcesRequest(
        source_type=source_type,
        domain=domain,
        enabled=enabled,
        limit=limit,
    )
    result = _list_sources(OperationContext(conn=ctx.conn), request)

    return {
        "sources": [
            {
                "id": s.id,
                "name": s.name,
                "source_type": s.source_type,
                "domain": s.domain,
                "enabled": s.enabled,
                "created_at": str(s.created_at) if s.created_at else None,
            }
            for s in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def get_source(source_id: str) -> dict[str, Any]:
    """Get detailed information about a data source.

    Args:
        source_id: Unique source identifier

    Returns:
        Source details including config and fetch history
    """
    from spine.ops.context import OperationContext
    from spine.ops.sources import get_source as _get_source

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    result = _get_source(OperationContext(conn=ctx.conn), source_id)

    if not result.success:
        return {"error": result.error_message}

    s = result.data
    return {
        "id": s.id,
        "name": s.name,
        "source_type": s.source_type,
        "domain": s.domain,
        "enabled": s.enabled,
        "config": s.config,
        "created_at": str(s.created_at) if s.created_at else None,
        "updated_at": str(s.updated_at) if s.updated_at else None,
    }


@mcp.tool()
async def register_source(
    name: str,
    source_type: str = "file",
    config: dict[str, Any] | None = None,
    domain: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Register a new data source.

    Args:
        name: Source name
        source_type: Type of source (file, http, database, s3, sftp)
        config: Source-specific configuration (e.g., URL, path)
        domain: Data domain for this source
        enabled: Whether the source is active

    Returns:
        Dictionary with source_id
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import CreateSourceRequest
    from spine.ops.sources import register_source as _register_source

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = CreateSourceRequest(
        name=name,
        source_type=source_type,
        config=config or {},
        domain=domain,
        enabled=enabled,
    )
    result = _register_source(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return result.data
