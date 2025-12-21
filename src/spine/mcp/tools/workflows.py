"""Workflow management MCP tools."""

from __future__ import annotations

from typing import Any

from spine.mcp import _app

mcp = _app.mcp


@mcp.tool()
async def list_workflows() -> dict[str, Any]:
    """List all registered workflows.

    Returns:
        Dictionary with 'workflows' list containing name, step_count, and description
    """
    from spine.ops.context import OperationContext
    from spine.ops.workflows import list_workflows as _list_workflows

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "workflows": []}

    result = _list_workflows(OperationContext(conn=ctx.conn))

    return {
        "workflows": [
            {
                "name": w.name,
                "step_count": w.step_count,
                "description": w.description,
            }
            for w in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def get_workflow(name: str) -> dict[str, Any]:
    """Get detailed information about a workflow.

    Args:
        name: Workflow name

    Returns:
        Workflow details including steps
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import GetWorkflowRequest
    from spine.ops.workflows import get_workflow as _get_workflow

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = GetWorkflowRequest(name=name)
    result = _get_workflow(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    wf = result.data
    return {
        "name": wf.name,
        "step_count": len(wf.steps),
        "steps": wf.steps,
        "description": wf.description,
        "metadata": wf.metadata,
    }


@mcp.tool()
async def run_workflow(
    name: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a workflow.

    Args:
        name: Workflow name
        params: Optional workflow parameters

    Returns:
        Dictionary with run_id
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import RunWorkflowRequest
    from spine.ops.workflows import run_workflow as _run_workflow

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = RunWorkflowRequest(name=name, params=params or {})
    result = _run_workflow(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return {"run_id": result.data.run_id, "submitted": True}
