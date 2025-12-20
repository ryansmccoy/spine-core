"""spine-core MCP Server Implementation.

Exposes spine-core workflow orchestration, run management, scheduling,
quality monitoring, and alerting capabilities as MCP tools.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from spine.core.transports.mcp import create_spine_mcp, run_spine_mcp

logger = logging.getLogger("spine.mcp")


@dataclass
class AppContext:
    """Application context for MCP server."""

    conn: Any = None  # Database connection
    initialized: bool = False


@asynccontextmanager
async def lifespan():
    """MCP server lifespan manager."""
    ctx = AppContext()

    # Import here to avoid requiring database at module load time
    try:
        from spine.core.database import get_connection

        ctx.conn = get_connection()
        ctx.initialized = True
        logger.info("spine-core MCP server initialized")
    except Exception as e:
        logger.warning("Database connection unavailable: %s", e)
        ctx.conn = None
        ctx.initialized = False

    yield ctx

    # Cleanup
    if ctx.conn:
        try:
            ctx.conn.close()
        except Exception:
            pass


# Create MCP server instance
mcp = create_spine_mcp(
    name="spine-core",
    instructions="""
spine-core orchestration and monitoring server.

Capabilities:
- Execute and monitor workflow runs
- Manage schedules
- Query quality metrics
- List alerts and anomalies
- Health checks

Use these tools to orchestrate data pipelines, track execution status,
and monitor data quality across your spine-based workflows.
""",
    lifespan=lifespan,
)


# ================================================================
# Run Management Tools
# ================================================================


@mcp.tool()
async def list_runs(
    status: str | None = None,
    workflow: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List workflow and pipeline runs.

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

    ctx = _get_context()
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

    ctx = _get_context()
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
    """Submit a new workflow or pipeline run.

    Args:
        kind: Type of work ('workflow' or 'pipeline')
        name: Workflow or pipeline name
        params: Optional parameters for the run
        priority: Priority level (realtime, high, normal, low)

    Returns:
        Dictionary with run_id of the submitted run
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import SubmitRunRequest
    from spine.ops.runs import submit_run as _submit_run

    ctx = _get_context()
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
    """Cancel a running workflow or pipeline.

    Args:
        run_id: Unique run identifier
        reason: Optional cancellation reason

    Returns:
        Confirmation of cancellation
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import CancelRunRequest
    from spine.ops.runs import cancel_run as _cancel_run

    ctx = _get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = CancelRunRequest(run_id=run_id, reason=reason)
    result = _cancel_run(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return {"cancelled": True, "run_id": run_id}


# ================================================================
# Workflow Management Tools
# ================================================================


@mcp.tool()
async def list_workflows() -> dict[str, Any]:
    """List all registered workflows.

    Returns:
        Dictionary with 'workflows' list containing name, step_count, and description
    """
    from spine.ops.context import OperationContext
    from spine.ops.workflows import list_workflows as _list_workflows

    ctx = _get_context()
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

    ctx = _get_context()
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

    ctx = _get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = RunWorkflowRequest(name=name, params=params or {})
    result = _run_workflow(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return {"run_id": result.data.run_id, "submitted": True}


# ================================================================
# Schedule Management Tools
# ================================================================


@mcp.tool()
async def list_schedules(limit: int = 50) -> dict[str, Any]:
    """List all configured schedules.

    Args:
        limit: Maximum number of schedules to return

    Returns:
        Dictionary with 'schedules' list
    """
    from spine.ops.context import OperationContext
    from spine.ops.schedules import list_schedules as _list_schedules

    ctx = _get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "schedules": []}

    result = _list_schedules(OperationContext(conn=ctx.conn))

    return {
        "schedules": [
            {
                "schedule_id": s.schedule_id,
                "name": s.name,
                "target_type": s.target_type,
                "target_name": s.target_name,
                "cron_expression": s.cron_expression,
                "enabled": s.enabled,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
            }
            for s in result.items[:limit]
        ],
        "total": result.total,
    }


@mcp.tool()
async def create_schedule(
    name: str,
    target_name: str,
    cron_expression: str | None = None,
    interval_seconds: int | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Create a new schedule.

    Args:
        name: Schedule name
        target_name: Workflow or pipeline to execute
        cron_expression: Cron expression (e.g., '0 */4 * * *')
        interval_seconds: Alternative to cron, interval in seconds
        enabled: Whether schedule is active

    Returns:
        Dictionary with schedule_id
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import CreateScheduleRequest
    from spine.ops.schedules import create_schedule as _create_schedule

    ctx = _get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = CreateScheduleRequest(
        name=name,
        target_name=target_name,
        cron_expression=cron_expression,
        interval_seconds=interval_seconds,
        enabled=enabled,
    )

    result = _create_schedule(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return {"schedule_id": result.data.schedule_id, "created": True}


# ================================================================
# Quality & Monitoring Tools
# ================================================================


@mcp.tool()
async def list_quality_results(
    workflow: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List quality check results.

    Args:
        workflow: Filter by workflow name
        limit: Maximum results to return

    Returns:
        Dictionary with quality results
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import ListQualityResultsRequest
    from spine.ops.quality import list_quality_results as _list_quality_results

    ctx = _get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "results": []}

    request = ListQualityResultsRequest(workflow=workflow, limit=limit)
    result = _list_quality_results(OperationContext(conn=ctx.conn), request)

    return {
        "results": [
            {
                "workflow": qr.workflow,
                "checks_passed": qr.checks_passed,
                "checks_failed": qr.checks_failed,
                "score": qr.score,
                "run_at": qr.run_at.isoformat() if qr.run_at else None,
            }
            for qr in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def list_anomalies(
    workflow: str | None = None,
    severity: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List detected anomalies.

    Args:
        workflow: Filter by workflow name
        severity: Filter by severity (LOW, MEDIUM, HIGH, CRITICAL)
        limit: Maximum anomalies to return

    Returns:
        Dictionary with anomalies list
    """
    from spine.ops.anomalies import list_anomalies as _list_anomalies
    from spine.ops.context import OperationContext
    from spine.ops.requests import ListAnomaliesRequest

    ctx = _get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "anomalies": []}

    request = ListAnomaliesRequest(workflow=workflow, severity=severity, limit=limit)
    result = _list_anomalies(OperationContext(conn=ctx.conn), request)

    return {
        "anomalies": [
            {
                "id": a.id,
                "workflow": a.workflow,
                "metric": a.metric,
                "severity": a.severity,
                "value": a.value,
                "threshold": a.threshold,
                "detected_at": a.detected_at.isoformat() if a.detected_at else None,
            }
            for a in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def list_alerts(
    severity: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List system alerts.

    Args:
        severity: Filter by severity (ERROR, WARN, INFO)
        limit: Maximum alerts to return

    Returns:
        Dictionary with alerts list
    """
    from spine.ops.alerts import list_alerts as _list_alerts
    from spine.ops.context import OperationContext
    from spine.ops.requests import ListAlertsRequest

    ctx = _get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "alerts": []}

    request = ListAlertsRequest(severity=severity, limit=limit)
    result = _list_alerts(OperationContext(conn=ctx.conn), request)

    return {
        "alerts": [
            {
                "id": a.id,
                "severity": a.severity,
                "title": a.title,
                "message": a.message,
                "source": a.source,
                "created_at": str(a.created_at) if a.created_at else None,
            }
            for a in result.items
        ],
        "total": result.total,
    }


# ================================================================
# Health & System Tools
# ================================================================


@mcp.tool()
async def health_check() -> dict[str, Any]:
    """Check system health status.

    Returns:
        Health status including database connectivity
    """
    from spine.ops.context import OperationContext
    from spine.ops.database import check_database_health

    ctx = _get_context()
    if not ctx.initialized:
        return {
            "status": "unhealthy",
            "database": {"connected": False},
            "version": _get_version(),
        }

    result = check_database_health(OperationContext(conn=ctx.conn))

    if not result.success:
        return {
            "status": "unhealthy",
            "database": {"connected": False},
            "error": result.error_message,
            "version": _get_version(),
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
        "version": _get_version(),
    }


# ================================================================
# Helper Functions
# ================================================================


def _get_context() -> AppContext:
    """Get current MCP context."""
    # Context is available via mcp.request_context in actual tool execution
    # For now, create a new connection each time
    from spine.core.database import get_connection

    try:
        conn = get_connection()
        return AppContext(conn=conn, initialized=True)
    except Exception:
        return AppContext(conn=None, initialized=False)


def _get_version() -> str:
    """Get spine-core version."""
    try:
        from spine import __version__

        return __version__
    except Exception:
        return "unknown"


# ================================================================
# Entry Point
# ================================================================


def create_server():
    """Create and return the MCP server instance."""
    return mcp


def run():
    """Run the MCP server (entry point for console script)."""
    run_spine_mcp(mcp, default_port=8100, log_name="spine-core-mcp")


if __name__ == "__main__":
    run()
