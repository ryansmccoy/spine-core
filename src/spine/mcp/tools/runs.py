"""Run management MCP tools."""

from __future__ import annotations

from typing import Any

from spine.mcp import _app

mcp = _app.mcp


@mcp.tool()
async def list_runs(
    status: str | None = None,
    workflow: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List workflow and operation runs.

    Args:
        status: Filter by status (PENDING, RUNNING, COMPLETED, FAILED)
        workflow: Filter by workflow name
        limit: Maximum number of runs to return (default: 20, max: 100)

    Returns:
        Dictionary with 'runs' list and 'total' count
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import ListRunsRequest
    from spine.ops.runs import list_runs as _list_runs

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "runs": [], "total": 0}

    request = ListRunsRequest(
        status=status,
        workflow=workflow,
        limit=min(limit, 100),
    )

    result = _list_runs(OperationContext(conn=ctx.conn), request)

    return {
        "runs": [
            {
                "run_id": r.run_id,
                "workflow": r.workflow,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "duration_ms": r.duration_ms,
            }
            for r in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def get_run(run_id: str) -> dict[str, Any]:
    """Get detailed information about a specific run.

    Args:
        run_id: Unique run identifier

    Returns:
        Run details including status, params, result, and error
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import GetRunRequest
    from spine.ops.runs import get_run as _get_run

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = GetRunRequest(run_id=run_id)
    result = _get_run(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    run = result.data
    return {
        "run_id": run.run_id,
        "workflow": run.workflow,
        "status": run.status,
        "params": run.params,
        "result": run.result,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms,
        "events": [
            {
                "event_type": e.get("event_type"),
                "timestamp": e.get("timestamp"),
                "message": e.get("message"),
            }
            for e in (run.events or [])
        ],
    }


@mcp.tool()
async def submit_run(
    kind: str,
    name: str,
    params: dict[str, Any] | None = None,
    priority: str = "normal",
) -> dict[str, Any]:
    """Submit a new workflow or operation run.

    Args:
        kind: Type of work ('workflow' or 'operation')
        name: Workflow or operation name
        params: Optional parameters for the run
        priority: Priority level (realtime, high, normal, low)

    Returns:
        Dictionary with run_id of the submitted run
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import SubmitRunRequest
    from spine.ops.runs import submit_run as _submit_run

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = SubmitRunRequest(
        kind=kind,
        name=name,
        params=params or {},
        priority=priority,
    )

    result = _submit_run(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return {"run_id": result.data.run_id, "submitted": True}


@mcp.tool()
async def cancel_run(run_id: str, reason: str | None = None) -> dict[str, Any]:
    """Cancel a running workflow or operation.

    Args:
        run_id: Unique run identifier
        reason: Optional cancellation reason

    Returns:
        Confirmation of cancellation
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import CancelRunRequest
    from spine.ops.runs import cancel_run as _cancel_run

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = CancelRunRequest(run_id=run_id, reason=reason)
    result = _cancel_run(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return {"cancelled": True, "run_id": run_id}


@mcp.tool()
async def retry_run(run_id: str) -> dict[str, Any]:
    """Retry a failed or dead-lettered run.

    Re-queues the run for execution. Only runs in 'failed' or
    'dead_lettered' status can be retried.

    Args:
        run_id: Unique run identifier

    Returns:
        Confirmation with original run_id
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import RetryRunRequest
    from spine.ops.runs import retry_run as _retry_run

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = RetryRunRequest(run_id=run_id)
    result = _retry_run(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return {"retried": True, "run_id": run_id}


@mcp.tool()
async def get_run_events(
    run_id: str,
    limit: int = 100,
) -> dict[str, Any]:
    """Get the event-sourced history for a run.

    Returns all events (submitted, started, completed, failed, etc.)
    that occurred during the run's lifecycle.

    Args:
        run_id: Unique run identifier
        limit: Maximum events to return (default: 100, max: 500)

    Returns:
        Dictionary with 'events' list and 'total' count
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import GetRunEventsRequest
    from spine.ops.runs import get_run_events as _get_run_events

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "events": [], "total": 0}

    request = GetRunEventsRequest(run_id=run_id, limit=min(limit, 500))
    result = _get_run_events(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message, "events": [], "total": 0}

    return {
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "timestamp": str(e.timestamp) if e.timestamp else None,
                "message": e.message,
            }
            for e in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def get_run_steps(
    run_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Get step-level timing data for a workflow run.

    Returns detailed execution timing for each step, useful for
    performance analysis and bottleneck identification.

    Args:
        run_id: Unique run identifier
        limit: Maximum steps to return (default: 50, max: 200)

    Returns:
        Dictionary with 'steps' list and 'total' count
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import GetRunStepsRequest
    from spine.ops.runs import get_run_steps as _get_run_steps

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "steps": [], "total": 0}

    request = GetRunStepsRequest(run_id=run_id, limit=min(limit, 200))
    result = _get_run_steps(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message, "steps": [], "total": 0}

    return {
        "steps": [
            {
                "step_id": s.step_id,
                "step_name": s.step_name,
                "step_type": s.step_type,
                "status": s.status,
                "started_at": str(s.started_at) if s.started_at else None,
                "completed_at": str(s.completed_at) if s.completed_at else None,
                "duration_ms": s.duration_ms,
                "attempt": s.attempt,
                "error": s.error,
            }
            for s in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def get_run_logs(
    run_id: str,
    step: str | None = None,
    level: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Get log entries for a run execution.

    Returns structured log lines from the execution, with optional
    filtering by step name and minimum log level.

    Args:
        run_id: Unique run identifier
        step: Filter by step name
        level: Minimum log level (DEBUG, INFO, WARN, ERROR)
        limit: Maximum log lines to return (default: 200, max: 1000)

    Returns:
        Dictionary with 'logs' list and 'total' count
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import GetRunLogsRequest
    from spine.ops.runs import get_run_logs as _get_run_logs

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "logs": [], "total": 0}

    request = GetRunLogsRequest(
        run_id=run_id,
        step=step,
        level=level,
        limit=min(limit, 1000),
    )
    result = _get_run_logs(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message, "logs": [], "total": 0}

    return {
        "logs": [
            {
                "timestamp": entry.timestamp,
                "level": entry.level,
                "message": entry.message,
                "step_name": entry.step_name,
                "logger": entry.logger,
            }
            for entry in result.items
        ],
        "total": result.total,
    }
