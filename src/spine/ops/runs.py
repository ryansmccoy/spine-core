"""
Run operations.

Read and control operations for execution runs across all work types
(tasks, operations, workflows, steps).  These wrap the internal
:class:`~spine.execution.dispatcher.EventDispatcher` with typed
request/response contracts.

.. note::

    The ``EventDispatcher`` is async-native.  These operations accept an
    optional pre-constructed dispatcher.  For API callers the async bridge
    happens at the transport layer (Phase 4); for CLI/SDK callers a sync
    shim can ``asyncio.run()`` the dispatcher methods.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from spine.core.logging import get_logger
from spine.core.repositories import ExecutionRepository, WorkflowRunRepository
from spine.ops.context import OperationContext
from spine.ops.requests import (
    CancelRunRequest,
    GetRunEventsRequest,
    GetRunLogsRequest,
    GetRunRequest,
    GetRunStepsRequest,
    ListRunsRequest,
    RetryRunRequest,
    SubmitRunRequest,
)
from spine.ops.responses import RunAccepted, RunDetail, RunEvent, RunLogEntry, RunSummary, StepTiming
from spine.ops.result import OperationResult, PagedResult, start_timer

logger = get_logger(__name__)


def _exec_repo(ctx: OperationContext) -> ExecutionRepository:
    """Create an ExecutionRepository from OperationContext."""
    return ExecutionRepository(ctx.conn)


def _wf_repo(ctx: OperationContext) -> WorkflowRunRepository:
    """Create a WorkflowRunRepository from OperationContext."""
    return WorkflowRunRepository(ctx.conn)


def list_runs(
    ctx: OperationContext,
    request: ListRunsRequest,
    *,
    dispatcher: Any = None,
) -> PagedResult[RunSummary]:
    """List runs with filtering and pagination.

    If *dispatcher* is ``None``, falls back to a database-level query using
    ``ctx.conn``.  When an ``EventDispatcher`` is provided, delegates to its
    ``list_runs`` method (requires async bridge at the caller).

    Args:
        ctx: Operation context with database connection.
        request: Filtering and pagination parameters.
        dispatcher: Optional ``EventDispatcher`` instance.

    Returns:
        Paged list of :class:`RunSummary` items.
    """
    timer = start_timer()

    try:
        runs, total = _query_runs(ctx, request)
        summaries = [_row_to_summary(r) for r in runs]
        return PagedResult.from_items(
            summaries,
            total=total,
            limit=request.limit,
            offset=request.offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to list runs: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


def get_run(
    ctx: OperationContext,
    request: GetRunRequest,
) -> OperationResult[RunDetail]:
    """Return full detail for a single run."""
    timer = start_timer()

    if not request.run_id:
        return OperationResult.fail(
            "VALIDATION_FAILED",
            "run_id is required",
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        row = _fetch_run_row(ctx, request.run_id)
        if row is None:
            return OperationResult.fail(
                "NOT_FOUND",
                f"Run '{request.run_id}' not found",
                elapsed_ms=timer.elapsed_ms,
            )
        return OperationResult.ok(_row_to_detail(row), elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to get run: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def cancel_run(
    ctx: OperationContext,
    request: CancelRunRequest,
) -> OperationResult[None]:
    """Cancel a running or queued execution."""
    timer = start_timer()

    if not request.run_id:
        return OperationResult.fail(
            "VALIDATION_FAILED",
            "run_id is required",
            elapsed_ms=timer.elapsed_ms,
        )

    if ctx.dry_run:
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)

    try:
        repo = _exec_repo(ctx)
        row = repo.get_by_id(request.run_id)
        if row is None:
            return OperationResult.fail("NOT_FOUND", f"Run '{request.run_id}' not found")

        status = row.get("status", "")
        if status in ("completed", "failed", "cancelled", "dead_lettered"):
            return OperationResult.fail(
                "NOT_CANCELLABLE",
                f"Run is already in terminal status '{status}'",
            )

        repo.update_status(request.run_id, "cancelled")
        repo.commit()

        # Publish cancellation event
        from spine.core.events import publish_event
        publish_event(
            "run.cancelled",
            "ops.runs",
            {
                "run_id": request.run_id,
                "reason": request.reason,
                "previous_status": status,
            },
            correlation_id=ctx.request_id,
        )

        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to cancel run: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def retry_run(
    ctx: OperationContext,
    request: RetryRunRequest,
) -> OperationResult[RunAccepted]:
    """Re-queue a failed run.

    Creates a reference to the original for traceability.  The actual
    re-submission happens through the ``EventDispatcher`` at the transport
    layer — this operation just records the intent.
    """
    timer = start_timer()

    if not request.run_id:
        return OperationResult.fail(
            "VALIDATION_FAILED",
            "run_id is required",
            elapsed_ms=timer.elapsed_ms,
        )

    if ctx.dry_run:
        return OperationResult.ok(
            RunAccepted(run_id=None, dry_run=True, would_execute=True),
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        repo = _exec_repo(ctx)
        row = repo.get_by_id(request.run_id)
        if row is None:
            return OperationResult.fail("NOT_FOUND", f"Run '{request.run_id}' not found")

        status = row.get("status", "")
        if status not in ("failed", "dead_lettered"):
            return OperationResult.fail(
                "VALIDATION_FAILED",
                f"Only failed/dead-lettered runs can be retried, current status: '{status}'",
            )

        return OperationResult.ok(
            RunAccepted(run_id=request.run_id, would_execute=True),
            elapsed_ms=timer.elapsed_ms,
            metadata={"retry_of": request.run_id},
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to retry run: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def submit_run(
    ctx: OperationContext,
    request: SubmitRunRequest,
) -> OperationResult[RunAccepted]:
    """Submit a new execution run (task, operation, or workflow).

    Inserts a row into ``core_executions`` with *pending* status and returns
    the allocated ``run_id``.  When ``ctx.dry_run`` is set, validates the
    request but does not persist anything.
    """
    import uuid
    from datetime import datetime

    timer = start_timer()

    if not request.name:
        return OperationResult.fail(
            "VALIDATION_FAILED",
            "name is required",
            elapsed_ms=timer.elapsed_ms,
        )
    if request.kind not in ("task", "operation", "workflow"):
        return OperationResult.fail(
            "VALIDATION_FAILED",
            f"Invalid kind '{request.kind}'; must be task, operation, or workflow",
            elapsed_ms=timer.elapsed_ms,
        )

    if ctx.dry_run:
        return OperationResult.ok(
            RunAccepted(run_id=None, dry_run=True, would_execute=True),
            elapsed_ms=timer.elapsed_ms,
        )

    run_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    # Encode kind and name so the worker can resolve the handler.
    # Convention: workflow column stores "kind:name" (e.g. "task:send_email").
    workflow_key = f"{request.kind}:{request.name}"
    params_json = "{}"
    if request.params:
        import json as _json
        try:
            params_json = _json.dumps(request.params)
        except (TypeError, ValueError):
            params_json = "{}"

    try:
        repo = _exec_repo(ctx)
        repo.create_execution({
            "id": run_id,
            "workflow": workflow_key,
            "status": "pending",
            "created_at": now,
            "params": params_json,
            "lane": request.priority or "default",
        })
        # Record a "submitted" event
        repo.add_event({
            "id": str(uuid.uuid4()),
            "execution_id": run_id,
            "event_type": "submitted",
            "timestamp": now,
            "data": "{}",
        })
        repo.commit()

        # Publish to EventBus for cross-app notifications
        from spine.core.events import publish_event
        publish_event(
            "run.submitted",
            "ops.runs",
            {
                "run_id": run_id,
                "kind": request.kind,
                "name": request.name,
                "priority": request.priority,
            },
            correlation_id=ctx.request_id,
        )

        return OperationResult.ok(
            RunAccepted(run_id=run_id, would_execute=True),
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to submit run: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def get_run_events(
    ctx: OperationContext,
    request: GetRunEventsRequest,
) -> PagedResult[RunEvent]:
    """Return the event-sourced history for a run."""
    timer = start_timer()

    if not request.run_id:
        return PagedResult(
            success=False,
            error=_err("VALIDATION_FAILED", "run_id is required"),
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        repo = _exec_repo(ctx)
        rows_raw, total = repo.list_events(
            request.run_id, limit=request.limit, offset=request.offset,
        )

        events: list[RunEvent] = []
        for d in rows_raw:
            events.append(RunEvent(
                event_id=d.get("id", ""),
                run_id=d.get("execution_id", request.run_id),
                event_type=d.get("event_type", ""),
                timestamp=d.get("timestamp"),
                message=d.get("message", ""),
            ))

        return PagedResult.from_items(
            events,
            total=total,
            limit=request.limit,
            offset=request.offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to get run events: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


def get_run_steps(
    ctx: OperationContext,
    request: GetRunStepsRequest,
) -> PagedResult[StepTiming]:
    """Return step-level timing data for a workflow run.

    Queries the core_workflow_steps table to provide detailed execution
    timing for each step in a workflow run. Essential for performance
    analysis and bottleneck identification.
    """
    timer = start_timer()

    if not request.run_id:
        return PagedResult(
            success=False,
            error=_err("VALIDATION_FAILED", "run_id is required"),
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        wf = _wf_repo(ctx)
        rows_raw, total = wf.list_steps(
            request.run_id, limit=request.limit, offset=request.offset,
        )

        steps: list[StepTiming] = []
        for d in rows_raw:
            # Parse metrics JSON if present
            metrics_raw = d.get("metrics")
            metrics: dict = {}
            if isinstance(metrics_raw, str):
                import json
                try:
                    metrics = json.loads(metrics_raw)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(metrics_raw, dict):
                metrics = metrics_raw

            steps.append(StepTiming(
                step_id=d.get("step_id", ""),
                run_id=d.get("run_id", request.run_id),
                step_name=d.get("step_name", ""),
                step_type=d.get("step_type", ""),
                step_order=d.get("step_order", 0),
                status=d.get("status", ""),
                started_at=d.get("started_at"),
                completed_at=d.get("completed_at"),
                duration_ms=d.get("duration_ms"),
                row_count=d.get("row_count"),
                attempt=d.get("attempt", 1),
                max_attempts=d.get("max_attempts", 1),
                error=d.get("error"),
                error_category=d.get("error_category"),
                metrics=metrics,
            ))

        return PagedResult.from_items(
            steps,
            total=total,
            limit=request.limit,
            offset=request.offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to get run steps: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #

def _query_runs(
    ctx: OperationContext,
    request: ListRunsRequest,
) -> tuple[list[dict[str, Any]], int]:
    """Query execution rows from the database via repository."""
    repo = _exec_repo(ctx)
    return repo.list_executions(
        workflow=request.workflow,
        status=request.status,
        limit=request.limit,
        offset=request.offset,
    )


def _fetch_run_row(ctx: OperationContext, run_id: str) -> dict[str, Any] | None:
    """Fetch a single run row by ID via repository."""
    repo = _exec_repo(ctx)
    return repo.get_by_id(run_id)


def _row_to_summary(row: dict[str, Any]) -> RunSummary:
    """Convert a DB row dict to a :class:`RunSummary`."""
    return RunSummary(
        run_id=row.get("id", ""),
        workflow=row.get("workflow"),
        status=row.get("status", ""),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        duration_ms=row.get("duration_ms"),
    )


def _row_to_detail(row: dict[str, Any]) -> RunDetail:
    """Convert a DB row dict to a :class:`RunDetail`."""
    return RunDetail(
        run_id=row.get("id", ""),
        workflow=row.get("workflow"),
        status=row.get("status", ""),
        params=row.get("params") if isinstance(row.get("params"), dict) else {},
        result=row.get("result") if isinstance(row.get("result"), dict) else None,
        error=row.get("error"),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        duration_ms=row.get("duration_ms"),
    )


def _err(code: str, message: str):
    """Shorthand to create an OperationError."""
    from spine.ops.result import OperationError
    return OperationError(code=code, message=message)


# ------------------------------------------------------------------ #
# Run log operations
# ------------------------------------------------------------------ #


# Log level hierarchy for filtering
_LOG_LEVELS = {"DEBUG": 0, "INFO": 1, "WARN": 2, "WARNING": 2, "ERROR": 3}


def get_run_logs(
    ctx: OperationContext,
    request: GetRunLogsRequest,
) -> PagedResult[RunLogEntry]:
    """Get log entries for a run execution.

    Returns structured log lines from the execution, supporting
    filtering by step name and minimum log level.

    Args:
        ctx: Operation context with database connection.
        request: Log query parameters (run_id, step, level, limit, offset).

    Returns:
        Paged list of :class:`RunLogEntry` items.

    Raises:
        VALIDATION_FAILED: Missing run_id.
        NOT_FOUND: Run does not exist.
    """
    timer = start_timer()

    if not request.run_id:
        return PagedResult(
            success=False,
            error=_err("VALIDATION_FAILED", "run_id is required"),
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        # Verify run exists
        row = _fetch_run_row(ctx, request.run_id)
        if row is None:
            return PagedResult(
                success=False,
                error=_err("NOT_FOUND", f"Run '{request.run_id}' not found"),
                elapsed_ms=timer.elapsed_ms,
            )

        logs, total = _query_run_logs(ctx, request)
        entries = [_row_to_log_entry(r) for r in logs]
        return PagedResult.from_items(
            entries,
            total=total,
            limit=request.limit,
            offset=request.offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to get run logs: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


def _query_run_logs(
    ctx: OperationContext,
    request: GetRunLogsRequest,
) -> tuple[list[dict], int]:
    """Query log entries from the database."""
    conn = ctx.conn

    # Build WHERE clauses
    wheres = ["run_id = ?"]
    params: list = [request.run_id]

    if request.step:
        wheres.append("step_name = ?")
        params.append(request.step)

    if request.level:
        # Filter to this level and above
        level_num = _LOG_LEVELS.get(request.level.upper(), 1)
        level_names = [k for k, v in _LOG_LEVELS.items() if v >= level_num]
        if level_names:
            placeholders = ",".join("?" * len(level_names))
            wheres.append(f"UPPER(level) IN ({placeholders})")
            params.extend(level_names)

    where_clause = " AND ".join(wheres)

    # Get total count
    count_sql = f"SELECT COUNT(*) FROM core_execution_logs WHERE {where_clause}"
    conn.execute(count_sql, tuple(params))
    count_row = conn.fetchone()
    total = count_row[0] if count_row else 0

    # Get paginated results
    sql = f"""
        SELECT id, run_id, step_name, level, message, logger, timestamp, line_number
        FROM core_execution_logs
        WHERE {where_clause}
        ORDER BY line_number ASC, timestamp ASC
        LIMIT ? OFFSET ?
    """
    conn.execute(sql, tuple(params + [request.limit, request.offset]))
    rows = conn.fetchall()

    # Convert rows to dicts
    result = []
    for row in rows:
        if isinstance(row, dict):
            result.append(row)
        elif hasattr(row, "keys"):
            result.append(dict(row))
        else:
            result.append({
                "id": row[0] if len(row) > 0 else 0,
                "run_id": row[1] if len(row) > 1 else "",
                "step_name": row[2] if len(row) > 2 else None,
                "level": row[3] if len(row) > 3 else "INFO",
                "message": row[4] if len(row) > 4 else "",
                "logger": row[5] if len(row) > 5 else "",
                "timestamp": row[6] if len(row) > 6 else "",
                "line_number": row[7] if len(row) > 7 else 0,
            })

    return result, total


def _row_to_log_entry(row: dict) -> RunLogEntry:
    """Convert a DB row dict to a :class:`RunLogEntry`."""
    return RunLogEntry(
        timestamp=row.get("timestamp", ""),
        level=row.get("level", "INFO"),
        message=row.get("message", ""),
        step_name=row.get("step_name"),
        logger=row.get("logger", ""),
        line_number=row.get("line_number", 0),
    )