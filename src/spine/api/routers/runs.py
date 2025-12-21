"""
Runs router — list, inspect, cancel, and retry execution runs.

Provides CRUD and control operations for execution runs across all work types
(tasks, operations, workflows). This is the primary endpoint set for the
orchestration console's Runs view.

Endpoints:
    POST   /runs              Submit a new run
    GET    /runs              List runs with filtering/pagination
    GET    /runs/{run_id}     Get full run detail
    POST   /runs/{run_id}/cancel   Cancel a running execution
    POST   /runs/{run_id}/retry    Retry a failed execution
    GET    /runs/{run_id}/events   Get event history for a run

Manifesto:
    Submitting and tracking runs via REST enables both UI
    dashboards and CI/CD pipelines to interact with execution.

Tags:
    spine-core, api, runs, submission, status, lifecycle

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field

from spine.api.deps import OpContext
from spine.api.schemas.common import PagedResponse, PageMeta, SuccessResponse
from spine.api.schemas.domains import (
    RunAcceptedSchema,
    RunDetailSchema,
    RunEventSchema,
    RunLogEntrySchema,
    RunStepSchema,
    RunSummarySchema,
)
from spine.api.utils import _dc, _handle_error

router = APIRouter(prefix="/runs")


class CancelBody(BaseModel):
    """Request body for cancelling a run.

    Attributes:
        reason: Optional human-readable reason for cancellation.
                Stored in run events for audit purposes.
    """

    reason: str = Field(
        default="",
        description="Optional reason for cancellation (for audit trail)",
    )


class SubmitRunBody(BaseModel):
    """Request body for submitting a new run.

    Attributes:
        kind: Work type — ``"task"``, ``"operation"``, or ``"workflow"``.
        name: Handler or workflow name to execute.
        params: Arbitrary runtime parameters passed to the execution.
        idempotency_key: Optional key for at-most-once execution semantics.
        priority: Execution priority lane (affects queue ordering).
        metadata: Freeform metadata attached to the run for tracking.

    Example:
        {
            "kind": "workflow",
            "name": "daily_etl",
            "params": {"date": "2026-02-13"},
            "idempotency_key": "etl-2026-02-13",
            "priority": "high",
            "metadata": {"triggered_by": "scheduler"}
        }
    """

    kind: str = Field(
        default="task",
        description="Work type: 'task' | 'operation' | 'workflow'",
    )
    name: str = Field(description="Handler or workflow name to execute")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime parameters for the execution",
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Deduplication key (prevents duplicate executions)",
    )
    priority: str = Field(
        default="normal",
        description="Priority lane: 'realtime' | 'high' | 'normal' | 'low'",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Freeform metadata for tracking/filtering",
    )


@router.post("", response_model=SuccessResponse[RunAcceptedSchema], status_code=202)
def submit_run(ctx: OpContext, body: SubmitRunBody):
    """Submit a new execution run (task, operation, or workflow).

    Queues work for execution and returns immediately with a run_id.
    The actual execution happens asynchronously via workers.

    Args:
        ctx: Operation context with database connection.
        body: Run submission parameters.

    Returns:
        SuccessResponse containing RunAcceptedSchema with the assigned run_id.
        Status code 202 indicates accepted for processing.

    Raises:
        400 VALIDATION_FAILED: Invalid kind or missing name.
        409 CONFLICT: Idempotency key collision (run already exists).

    Example:
        POST /api/v1/runs
        {"kind": "workflow", "name": "daily_etl", "params": {"date": "2026-02-13"}}

        Response (202):
        {"data": {"run_id": "abc-123", "dry_run": false, "would_execute": true}}
    """
    from spine.ops.requests import SubmitRunRequest
    from spine.ops.runs import submit_run as _submit

    request = SubmitRunRequest(
        kind=body.kind,
        name=body.name,
        params=body.params,
        idempotency_key=body.idempotency_key,
        priority=body.priority,
        metadata=body.metadata,
    )
    result = _submit(ctx, request)
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=RunAcceptedSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.get("", response_model=PagedResponse[RunSummarySchema])
def list_runs(
    ctx: OpContext,
    kind: str | None = Query(None, description="Filter by work type: 'task' | 'operation' | 'workflow'"),
    status: str | None = Query(None, description="Filter by status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'dead_lettered'"),
    workflow: str | None = Query(None, description="Filter by workflow name"),
    since: datetime | None = Query(None, description="Only runs started after this datetime (inclusive, ISO 8601)"),
    until: datetime | None = Query(None, description="Only runs started before this datetime (exclusive, ISO 8601)"),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return (1-500)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List execution runs with filtering and pagination.

    Returns a paged list of runs ordered by start time (newest first).
    All filter parameters are optional and can be combined.

    Args:
        ctx: Operation context with database connection.
        kind: Optional filter by work type.
        status: Optional filter by execution status.
        workflow: Optional filter by workflow name.
        limit: Maximum items per page (default 50, max 500).
        offset: Pagination offset (default 0).

    Returns:
        PagedResponse containing list of RunSummarySchema items with pagination metadata.

    Example:
        GET /api/v1/runs?status=failed&limit=10

        Response:
        {
            "data": [{"run_id": "abc-123", "status": "failed", ...}],
            "page": {"total": 42, "limit": 10, "offset": 0, "has_more": true}
        }
    """
    from spine.ops.requests import ListRunsRequest
    from spine.ops.runs import list_runs as _list

    request = ListRunsRequest(
        kind=kind,
        status=status,
        workflow=workflow,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)
    if not result.success:
        return _handle_error(result)
    items = [RunSummarySchema(**_dc(r)) for r in (result.data or [])]
    return PagedResponse(
        data=items,
        page=PageMeta(
            total=result.total or 0,
            limit=result.limit or limit,
            offset=result.offset or offset,
            has_more=result.has_more or False,
        ),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.get("/{run_id}", response_model=SuccessResponse[RunDetailSchema])
def get_run(ctx: OpContext, run_id: str = Path(..., description="Run UUID")):
    """Get detailed information about a single run.

    Returns full run data including parameters, result, error, and events.
    Use this for the run detail drawer/modal in the orchestration console.

    Args:
        ctx: Operation context with database connection.
        run_id: The unique run identifier (UUID format).

    Returns:
        SuccessResponse containing RunDetailSchema with full run data.

    Raises:
        404 NOT_FOUND: Run with specified ID does not exist.

    Example:
        GET /api/v1/runs/abc-123-def-456

        Response:
        {
            "data": {
                "run_id": "abc-123-def-456",
                "status": "completed",
                "params": {"date": "2026-02-13"},
                "result": {"rows_processed": 1000},
                "events": [...]
            }
        }
    """
    from spine.ops.requests import GetRunRequest
    from spine.ops.runs import get_run as _get

    result = _get(ctx, GetRunRequest(run_id=run_id))
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=RunDetailSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.post("/{run_id}/cancel", response_model=SuccessResponse[RunAcceptedSchema])
def cancel_run(ctx: OpContext, run_id: str = Path(..., description="Run UUID"), body: CancelBody | None = None):
    """Cancel a running or queued execution.

    Sets the run status to 'cancelled' and stops further processing.
    Only works for runs in 'pending' or 'running' status.

    Args:
        ctx: Operation context with database connection.
        run_id: The unique run identifier to cancel.
        body: Optional cancellation reason.

    Returns:
        SuccessResponse confirming the cancellation.

    Raises:
        404 NOT_FOUND: Run with specified ID does not exist.
        409 NOT_CANCELLABLE: Run is already in a terminal status
            (completed, failed, cancelled, dead_lettered).

    Example:
        POST /api/v1/runs/abc-123/cancel
        {"reason": "User requested abort"}

        Response:
        {"data": {"run_id": "abc-123"}}
    """
    from spine.ops.requests import CancelRunRequest
    from spine.ops.runs import cancel_run as _cancel

    body = body or CancelBody()
    result = _cancel(ctx, CancelRunRequest(run_id=run_id, reason=body.reason))
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=RunAcceptedSchema(run_id=run_id),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.post("/{run_id}/retry", response_model=SuccessResponse[RunAcceptedSchema], status_code=202)
def retry_run(ctx: OpContext, run_id: str = Path(..., description="Run UUID")):
    """Retry a failed execution.

    Creates a new run with the same parameters as the original.
    Only works for runs in 'failed' or 'dead_lettered' status.

    Args:
        ctx: Operation context with database connection.
        run_id: The unique run identifier to retry.

    Returns:
        SuccessResponse containing RunAcceptedSchema with the new run_id.
        Status code 202 indicates the retry has been accepted.

    Raises:
        404 NOT_FOUND: Original run does not exist.
        409 CONFLICT: Run is not in a retryable status.

    Example:
        POST /api/v1/runs/abc-123/retry

        Response (202):
        {"data": {"run_id": "new-456-run"}}
    """
    from spine.ops.requests import RetryRunRequest
    from spine.ops.runs import retry_run as _retry

    result = _retry(ctx, RetryRunRequest(run_id=run_id))
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=RunAcceptedSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.get("/{run_id}/events", response_model=PagedResponse[RunEventSchema])
def get_run_events(
    ctx: OpContext,
    run_id: str = Path(..., description="Run UUID"),
    limit: int = Query(200, ge=1, le=1000, description="Maximum events to return (1-1000)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Get event-sourced history for a run.

    Returns the chronological list of events that occurred during execution.
    Useful for debugging, audit trails, and understanding execution flow.

    Args:
        ctx: Operation context with database connection.
        run_id: The unique run identifier.
        limit: Maximum events per page (default 200, max 1000).
        offset: Pagination offset (default 0).

    Returns:
        PagedResponse containing list of RunEventSchema items.

    Raises:
        404 NOT_FOUND: Run with specified ID does not exist.

    Example:
        GET /api/v1/runs/abc-123/events?limit=50

        Response:
        {
            "data": [
                {"event_id": "e1", "event_type": "started", "timestamp": "..."},
                {"event_id": "e2", "event_type": "step_completed", "message": "Step 1 done"}
            ],
            "page": {"total": 5, "limit": 50, "offset": 0, "has_more": false}
        }
    """
    from spine.ops.requests import GetRunEventsRequest
    from spine.ops.runs import get_run_events as _events

    result = _events(ctx, GetRunEventsRequest(run_id=run_id, limit=limit, offset=offset))
    if not result.success:
        return _handle_error(result)
    items = [RunEventSchema(**_dc(e)) for e in (result.data or [])]
    return PagedResponse(
        data=items,
        page=PageMeta(
            total=result.total or 0,
            limit=result.limit or limit,
            offset=result.offset or offset,
            has_more=result.has_more or False,
        ),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.get("/{run_id}/steps", response_model=PagedResponse[RunStepSchema])
def get_run_steps(
    ctx: OpContext,
    run_id: str = Path(..., description="Run UUID"),
    limit: int = Query(100, ge=1, le=500, description="Maximum steps to return (1-500)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Get step-level timing data for a workflow run.

    Returns timing and execution details for each step in a workflow run.
    Essential for performance analysis, bottleneck identification, and
    debugging failed workflows.

    Args:
        ctx: Operation context with database connection.
        run_id: The unique run identifier.
        limit: Maximum steps per page (default 100, max 500).
        offset: Pagination offset (default 0).

    Returns:
        PagedResponse containing list of RunStepSchema items with timing data.

    Raises:
        404 NOT_FOUND: Run with specified ID does not exist.

    Example:
        GET /api/v1/runs/abc-123/steps?limit=50

        Response:
        {
            "data": [
                {
                    "step_id": "s1",
                    "step_name": "fetch_data",
                    "step_type": "operation",
                    "status": "COMPLETED",
                    "duration_ms": 1250,
                    "row_count": 10000
                },
                {
                    "step_id": "s2",
                    "step_name": "transform",
                    "step_type": "task",
                    "status": "COMPLETED",
                    "duration_ms": 890
                }
            ],
            "page": {"total": 5, "limit": 50, "offset": 0, "has_more": false}
        }
    """
    from spine.ops.requests import GetRunStepsRequest
    from spine.ops.runs import get_run_steps as _steps

    result = _steps(ctx, GetRunStepsRequest(run_id=run_id, limit=limit, offset=offset))
    if not result.success:
        return _handle_error(result)
    items = [RunStepSchema(**_dc(s)) for s in (result.data or [])]
    return PagedResponse(
        data=items,
        page=PageMeta(
            total=result.total or 0,
            limit=result.limit or limit,
            offset=result.offset or offset,
            has_more=result.has_more or False,
        ),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.get("/{run_id}/logs", response_model=PagedResponse[RunLogEntrySchema])
def get_run_logs(
    ctx: OpContext,
    run_id: str = Path(..., description="Run UUID"),
    step: str | None = Query(None, description="Filter to specific step name"),
    level: str | None = Query(None, description="Minimum log level: DEBUG|INFO|WARN|ERROR"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum lines to return (1-10000)"),
    offset: int = Query(0, ge=0, description="Line offset for pagination"),
):
    """Get log entries for a run execution.

    Returns structured log lines emitted during run execution.
    Supports filtering by step name and minimum log level.
    Ordered chronologically (oldest first).

    Args:
        ctx: Operation context with database connection.
        run_id: The unique run identifier.
        step: Optional filter to logs from a specific step.
        level: Optional minimum log level filter (DEBUG shows all, ERROR shows only errors).
        limit: Maximum lines per page (default 1000, max 10000).
        offset: Pagination offset (default 0).

    Returns:
        PagedResponse containing list of RunLogEntrySchema items.

    Raises:
        404 NOT_FOUND: Run with specified ID does not exist.

    Example:
        GET /api/v1/runs/abc-123/logs?step=extract&level=ERROR&limit=500

        Response:
        {
            "data": [
                {
                    "timestamp": "2026-02-13T10:15:23.456Z",
                    "level": "ERROR",
                    "message": "Connection timeout after 30s",
                    "step_name": "extract",
                    "logger": "spine.operations.etl",
                    "line_number": 42
                }
            ],
            "page": {"total": 1, "limit": 500, "offset": 0, "has_more": false}
        }
    """
    from spine.ops.requests import GetRunLogsRequest
    from spine.ops.runs import get_run_logs as _logs

    result = _logs(ctx, GetRunLogsRequest(
        run_id=run_id,
        step=step,
        level=level,
        limit=limit,
        offset=offset,
    ))
    if not result.success:
        return _handle_error(result)
    items = [RunLogEntrySchema(**_dc(e)) for e in (result.data or [])]
    return PagedResponse(
        data=items,
        page=PageMeta(
            total=result.total or 0,
            limit=result.limit or limit,
            offset=result.offset or offset,
            has_more=result.has_more or False,
        ),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )