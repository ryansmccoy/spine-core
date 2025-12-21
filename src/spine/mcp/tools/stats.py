"""Statistics and metrics MCP tools."""

from __future__ import annotations

from typing import Any

from spine.mcp import _app

mcp = _app.mcp


@mcp.tool()
async def get_run_stats() -> dict[str, Any]:
    """Get aggregate run statistics grouped by status.

    Returns counts of runs in each status (pending, running,
    completed, failed, cancelled) plus a total count.

    Returns:
        Dictionary mapping status names to counts, plus 'total'
    """
    from spine.ops.stats import get_run_stats as _get_run_stats

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "total": 0}

    return _get_run_stats(ctx.conn)
