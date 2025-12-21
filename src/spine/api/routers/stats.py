"""
Stats router — run statistics, worker status, and queue depths.

Provides real-time operational metrics for the orchestration console.
Use for dashboard widgets, monitoring, and capacity planning.

Endpoints:
    GET /stats/runs           Aggregate run counts by status
    GET /stats/queues         Queue depths per priority lane
    GET /stats/workers        List active workers
    GET /stats/workers/stats  Aggregate worker statistics

Manifesto:
    Aggregate statistics should be available via API for executive
    dashboards and capacity planning without custom queries.

Tags:
    spine-core, api, stats, aggregation, dashboard

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from spine.api.deps import OpContext
from spine.api.schemas.common import SuccessResponse

router = APIRouter(prefix="/stats")


# ── Schemas ──────────────────────────────────────────────────────────


class RunStatsSchema(BaseModel):
    """Aggregate counts by execution status.

    UI Hints:
        Display as a status breakdown chart (pie/donut) or stat cards.
        Use status badge colors for visual consistency with runs table.
    """

    total: int = Field(default=0, description="Total run count across all statuses")
    pending: int = Field(default=0, description="Runs awaiting worker pickup")
    running: int = Field(default=0, description="Currently executing runs")
    completed: int = Field(default=0, description="Successfully finished runs")
    failed: int = Field(default=0, description="Runs that terminated with error")
    cancelled: int = Field(default=0, description="Manually cancelled runs")
    dead_lettered: int = Field(default=0, description="Runs moved to DLQ after retry exhaustion")


class QueueDepthSchema(BaseModel):
    """Pending work per priority lane.

    UI Hints:
        Display as a bar chart or queue visualization.
        Highlight high pending counts as potential bottlenecks.
    """

    lane: str = Field(description="Priority lane: 'realtime' | 'high' | 'normal' | 'low'")
    pending: int = Field(default=0, description="Items waiting in queue")
    running: int = Field(default=0, description="Items currently being processed")


class WorkerSchema(BaseModel):
    """Worker info exposed via the API.

    UI Hints:
        Display in a workers table with status indicator.
        Show uptime and throughput metrics.
    """

    worker_id: str = Field(description="Unique worker identifier")
    pid: int = Field(description="Operating system process ID")
    started_at: str = Field(description="ISO-8601 timestamp when worker started")
    poll_interval: float = Field(description="Queue polling interval in seconds")
    max_workers: int = Field(description="Maximum concurrent executions")
    status: str = Field(description="Worker status: 'idle' | 'busy' | 'draining'")
    runs_processed: int = Field(default=0, description="Total runs completed by this worker")
    runs_failed: int = Field(default=0, description="Total runs failed on this worker")
    hostname: str = Field(default="", description="Machine hostname")


class WorkerStatsSchema(BaseModel):
    """Aggregate worker statistics.

    UI Hints:
        Display as summary cards at top of workers dashboard.
        Highlight active_runs against capacity.
    """

    total_processed: int = Field(default=0, description="Total runs completed across all workers")
    total_failed: int = Field(default=0, description="Total failures across all workers")
    total_completed: int = Field(default=0, description="Successfully completed runs")
    uptime_seconds: float = Field(default=0, description="Aggregate uptime in seconds")
    active_runs: int = Field(default=0, description="Currently executing runs")


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/runs", response_model=SuccessResponse[RunStatsSchema])
def run_stats(ctx: OpContext):
    """Aggregate run counts grouped by status.

    Returns total counts for each execution status. Use for dashboard
    summary cards and status distribution charts.

    Args:
        ctx: Operation context with database connection.

    Returns:
        SuccessResponse containing RunStatsSchema with per-status counts.

    Example:
        GET /api/v1/stats/runs

        Response:
        {
            "data": {
                "total": 1250,
                "pending": 15,
                "running": 8,
                "completed": 1100,
                "failed": 120,
                "cancelled": 5,
                "dead_lettered": 2
            }
        }
    """
    from spine.ops.stats import get_run_stats

    counts = get_run_stats(ctx.conn)

    return SuccessResponse(data=RunStatsSchema(
        total=counts.get("total", 0),
        pending=counts.get("pending", 0),
        running=counts.get("running", 0),
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        cancelled=counts.get("cancelled", 0),
        dead_lettered=counts.get("dead_lettered", 0),
    ))


@router.get("/queues", response_model=SuccessResponse[list[QueueDepthSchema]])
def queue_depths(ctx: OpContext):
    """Queue depths per priority lane.

    Returns pending and running counts for each priority lane.
    Use for queue backlog visualization and capacity planning.

    Args:
        ctx: Operation context with database connection.

    Returns:
        SuccessResponse containing list of QueueDepthSchema items.

    Example:
        GET /api/v1/stats/queues

        Response:
        {
            "data": [
                {"lane": "high", "pending": 5, "running": 3},
                {"lane": "normal", "pending": 25, "running": 8},
                {"lane": "low", "pending": 100, "running": 2}
            ]
        }
    """
    from spine.ops.stats import get_queue_depths

    queue_list = get_queue_depths(ctx.conn)

    queues = [
        QueueDepthSchema(lane=q["lane"], pending=q["pending"], running=q["running"])
        for q in queue_list
    ]

    return SuccessResponse(data=queues)


@router.get("/workers", response_model=SuccessResponse[list[WorkerSchema]])
def worker_list():
    """List active workers in this process.

    Returns all workers currently registered in this API process.
    Use for worker monitoring and scaling decisions.

    Returns:
        SuccessResponse containing list of WorkerSchema items.

    Example:
        GET /api/v1/stats/workers

        Response:
        {
            "data": [
                {
                    "worker_id": "w-abc123",
                    "pid": 12345,
                    "started_at": "2026-02-13T08:00:00Z",
                    "status": "idle",
                    "runs_processed": 150,
                    "runs_failed": 3
                }
            ]
        }
    """
    from spine.ops.stats import get_active_workers

    workers = get_active_workers()
    return SuccessResponse(data=[
        WorkerSchema(
            worker_id=w.worker_id,
            pid=w.pid,
            started_at=w.started_at.isoformat(),
            poll_interval=w.poll_interval,
            max_workers=w.max_workers,
            status=w.status,
            runs_processed=w.runs_processed,
            runs_failed=w.runs_failed,
            hostname=w.hostname,
        )
        for w in workers
    ])


@router.get("/workers/stats", response_model=SuccessResponse[list[WorkerStatsSchema]])
def worker_stats():
    """Aggregate statistics for all active workers.

    Returns combined metrics across all workers for capacity overview.
    Use for dashboard summary cards and utilization monitoring.

    Returns:
        SuccessResponse containing list of WorkerStatsSchema items.

    Example:
        GET /api/v1/stats/workers/stats

        Response:
        {
            "data": [
                {
                    "total_processed": 5000,
                    "total_failed": 150,
                    "total_completed": 4850,
                    "uptime_seconds": 86400,
                    "active_runs": 8
                }
            ]
        }
    """
    from spine.ops.stats import get_worker_stats

    stats = get_worker_stats()
    return SuccessResponse(data=[WorkerStatsSchema(**s) for s in stats])


class RunHistoryBucketSchema(BaseModel):
    """Time-bucketed run counts for the activity chart.

    UI Hints:
        Display as a stacked bar chart with status-colored segments.
        X-axis: time bucket; Y-axis: count. Tooltip shows per-status detail.
    """

    bucket: str = Field(description="ISO-8601 timestamp for the start of this time bucket")
    completed: int = Field(default=0, description="Completed runs in this bucket")
    failed: int = Field(default=0, description="Failed runs in this bucket")
    running: int = Field(default=0, description="Running (or started) runs in this bucket")
    cancelled: int = Field(default=0, description="Cancelled runs in this bucket")


@router.get("/runs/history", response_model=SuccessResponse[list[RunHistoryBucketSchema]])
def run_history(
    ctx: OpContext,
    hours: int = Query(24, ge=1, le=168, description="Look-back window in hours (1-168)"),
    buckets: int = Query(24, ge=1, le=168, description="Number of time buckets (1-168)"),
):
    """Time-bucketed run counts for the dashboard activity chart.

    Divides the last *hours* into *buckets* equal intervals and counts
    runs per status in each interval.  Ideal for stacked bar charts on
    the dashboard.

    Args:
        ctx: Operation context with database connection.
        hours: Look-back window in hours (default 24, max 168 / 7 days).
        buckets: Number of time intervals to divide the window into.

    Returns:
        SuccessResponse containing list of RunHistoryBucketSchema items.

    Example:
        GET /api/v1/stats/runs/history?hours=24&buckets=24

        Response:
        {
            "data": [
                {"bucket": "2026-02-13T00:00:00+00:00", "completed": 5, "failed": 1, "running": 0, "cancelled": 0},
                {"bucket": "2026-02-13T01:00:00+00:00", "completed": 8, "failed": 0, "running": 2, "cancelled": 1}
            ]
        }
    """
    from spine.ops.stats import get_run_history

    data = get_run_history(ctx.conn, hours=hours, buckets=buckets)
    return SuccessResponse(data=[RunHistoryBucketSchema(**b) for b in data])


# ── Dashboard Composite ──────────────────────────────────────────────


from datetime import datetime, timezone
from typing import Any

from spine.api.schemas.domains import RunSummarySchema


class DashboardSummarySchema(BaseModel):
    """Aggregated dashboard data for the main overview page.

    UI Hints:
        Single request replaces multiple dashboard widget requests.
        Contains data for: stat cards, queue depth, recent runs, health.
        Refresh every 15-30 seconds via polling or SSE updates.
    """

    run_stats: RunStatsSchema = Field(description="Run counts by status for stat cards")
    queue_depths: list[QueueDepthSchema] = Field(description="Queue depths per priority lane")
    recent_runs: list[RunSummarySchema] = Field(description="Last 10 runs for recent activity")
    health: dict[str, Any] = Field(description="System health summary")
    activity: list[RunHistoryBucketSchema] = Field(description="Last 24h activity buckets for chart")
    updated_at: str = Field(description="ISO-8601 timestamp of this snapshot")


@router.get("/dashboard", response_model=SuccessResponse[DashboardSummarySchema])
def dashboard_summary(ctx: OpContext):
    """Aggregated dashboard data in a single request.

    Combines run stats, queue depths, recent runs, health status,
    and activity history into one response for the main dashboard.
    Eliminates the need for 5+ separate requests on page load.

    Args:
        ctx: Operation context with database connection.

    Returns:
        SuccessResponse containing DashboardSummarySchema.

    Example:
        GET /api/v1/stats/dashboard

        Response:
        {
            "data": {
                "run_stats": {"total": 1250, "pending": 15, ...},
                "queue_depths": [{"lane": "high", "pending": 5, "running": 3}, ...],
                "recent_runs": [{"run_id": "abc123", "status": "completed", ...}],
                "health": {"status": "healthy", "database": "connected"},
                "activity": [{"bucket": "2026-02-13T00:00:00Z", "completed": 5, ...}],
                "updated_at": "2026-02-13T10:30:00Z"
            }
        }
    """
    from spine.ops.requests import ListRunsRequest
    from spine.ops.runs import list_runs as _list_runs
    from spine.ops.stats import get_queue_depths, get_run_history, get_run_stats

    # Gather all dashboard data
    run_stats = get_run_stats(ctx.conn)
    queue_list = get_queue_depths(ctx.conn)
    activity = get_run_history(ctx.conn, hours=24, buckets=24)

    # Get recent runs
    recent_result = _list_runs(ctx, ListRunsRequest(limit=10, offset=0))
    recent_runs = []
    if recent_result.success and recent_result.data:
        for r in recent_result.data:
            recent_runs.append(RunSummarySchema(
                run_id=r.run_id,
                workflow=r.workflow,
                status=r.status,
                started_at=r.started_at.isoformat() if r.started_at else None,
                finished_at=r.finished_at.isoformat() if r.finished_at else None,
                duration_ms=r.duration_ms,
            ))

    # Simple health check
    health = {"status": "healthy", "database": "connected"}
    try:
        ctx.conn.execute("SELECT 1")
        ctx.conn.fetchone()
    except Exception:
        health = {"status": "degraded", "database": "disconnected"}

    return SuccessResponse(data=DashboardSummarySchema(
        run_stats=RunStatsSchema(
            total=run_stats.get("total", 0),
            pending=run_stats.get("pending", 0),
            running=run_stats.get("running", 0),
            completed=run_stats.get("completed", 0),
            failed=run_stats.get("failed", 0),
            cancelled=run_stats.get("cancelled", 0),
            dead_lettered=run_stats.get("dead_lettered", 0),
        ),
        queue_depths=[
            QueueDepthSchema(lane=q["lane"], pending=q["pending"], running=q["running"])
            for q in queue_list
        ],
        recent_runs=recent_runs,
        health=health,
        activity=[RunHistoryBucketSchema(**b) for b in activity],
        updated_at=datetime.now(timezone.utc).isoformat(),
    ))