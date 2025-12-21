"""Dead letter queue MCP tools."""

from __future__ import annotations

from typing import Any

from spine.mcp import _app

mcp = _app.mcp


@mcp.tool()
async def list_dead_letters(
    workflow: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List dead-lettered executions.

    Dead letters are runs that failed permanently and were moved
    out of the main execution queue for manual review.

    Args:
        workflow: Filter by workflow name
        limit: Maximum dead letters to return

    Returns:
        Dictionary with 'dead_letters' list and 'total' count
    """
    from spine.ops.context import OperationContext
    from spine.ops.dlq import list_dead_letters as _list_dead_letters
    from spine.ops.requests import ListDeadLettersRequest

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "dead_letters": [], "total": 0}

    request = ListDeadLettersRequest(workflow=workflow, limit=limit)
    result = _list_dead_letters(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message, "dead_letters": [], "total": 0}

    return {
        "dead_letters": [
            {
                "id": dl.id,
                "workflow": dl.workflow,
                "error": dl.error,
                "created_at": str(dl.created_at) if dl.created_at else None,
                "replay_count": dl.replay_count,
            }
            for dl in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def replay_dead_letter(dead_letter_id: str) -> dict[str, Any]:
    """Replay a dead-lettered execution.

    Re-queues the failed execution for another attempt. Increments
    the replay count for tracking purposes.

    Args:
        dead_letter_id: Unique dead letter identifier

    Returns:
        Confirmation of replay
    """
    from spine.ops.context import OperationContext
    from spine.ops.dlq import replay_dead_letter as _replay_dead_letter
    from spine.ops.requests import ReplayDeadLetterRequest

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = ReplayDeadLetterRequest(dead_letter_id=dead_letter_id)
    result = _replay_dead_letter(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return {"replayed": True, "dead_letter_id": dead_letter_id}
