"""
Schedule operations.

CRUD for cron/interval schedules that trigger workflow executions.

.. note::

    This module is a **Phase 1 stub**.  Full schedule backend integration
    (APScheduler, Celery Beat) will be implemented in Phase 3.  The
    operations contracts are defined here so Phase 4 (API) and Phase 5
    (CLI) can wire their routes without blocking on the scheduler runtime.
"""

from __future__ import annotations

import uuid
from typing import Any

from spine.core.repositories import (
    CalcDependencyRepository,
    DataReadinessRepository,
    ExpectedScheduleRepository,
    ScheduleOpsRepository,
)
from spine.ops.context import OperationContext
from spine.ops.requests import (
    CheckDataReadinessRequest,
    CreateScheduleRequest,
    DeleteScheduleRequest,
    GetScheduleRequest,
    ListCalcDependenciesRequest,
    ListExpectedSchedulesRequest,
    UpdateScheduleRequest,
)
from spine.ops.responses import (
    CalcDependencySummary,
    DataReadinessSummary,
    ExpectedScheduleSummary,
    ScheduleDetail,
    ScheduleSummary,
)
from spine.ops.result import OperationResult, PagedResult, start_timer


def _sched_repo(ctx: OperationContext) -> ScheduleOpsRepository:
    return ScheduleOpsRepository(ctx.conn)


def _calc_dep_repo(ctx: OperationContext) -> CalcDependencyRepository:
    return CalcDependencyRepository(ctx.conn)


def _exp_sched_repo(ctx: OperationContext) -> ExpectedScheduleRepository:
    return ExpectedScheduleRepository(ctx.conn)


def _readiness_repo(ctx: OperationContext) -> DataReadinessRepository:
    return DataReadinessRepository(ctx.conn)


def list_schedules(ctx: OperationContext) -> PagedResult[ScheduleSummary]:
    """List all configured schedules."""
    timer = start_timer()

    try:
        repo = _sched_repo(ctx)
        rows = repo.list_schedules()

        summaries = [
            ScheduleSummary(
                schedule_id=r.get("id", ""),
                name=r.get("name", ""),
                target_type=r.get("target_type", "pipeline"),
                target_name=r.get("target_name", ""),
                cron_expression=r.get("cron_expression"),
                interval_seconds=r.get("interval_seconds"),
                enabled=bool(r.get("enabled", True)),
                next_run_at=r.get("next_run_at"),
            )
            for r in rows
        ]
        return PagedResult.from_items(
            summaries,
            total=len(summaries),
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception:
        # Table may not exist yet (Phase 3)
        return PagedResult.from_items([], total=0, elapsed_ms=timer.elapsed_ms)


def get_schedule(
    ctx: OperationContext,
    request: GetScheduleRequest,
) -> OperationResult[ScheduleDetail]:
    """Get a schedule by ID."""
    timer = start_timer()

    if not request.schedule_id:
        return OperationResult.fail(
            "VALIDATION_FAILED", "schedule_id is required", elapsed_ms=timer.elapsed_ms
        )

    try:
        repo = _sched_repo(ctx)
        row = repo.get_by_id(request.schedule_id)
        if row is None:
            return OperationResult.fail(
                "NOT_FOUND",
                f"Schedule '{request.schedule_id}' not found",
                elapsed_ms=timer.elapsed_ms,
            )

        detail = ScheduleDetail(
            schedule_id=row.get("id", ""),
            name=row.get("name", ""),
            target_type=row.get("target_type", "pipeline"),
            target_name=row.get("target_name", ""),
            cron_expression=row.get("cron_expression"),
            interval_seconds=row.get("interval_seconds"),
            enabled=bool(row.get("enabled", True)),
        )
        return OperationResult.ok(detail, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL", f"Failed to get schedule: {exc}", elapsed_ms=timer.elapsed_ms
        )


def create_schedule(
    ctx: OperationContext,
    request: CreateScheduleRequest,
) -> OperationResult[ScheduleDetail]:
    """Create a new schedule."""
    timer = start_timer()

    if not request.target_name:
        return OperationResult.fail(
            "VALIDATION_FAILED", "target_name is required", elapsed_ms=timer.elapsed_ms
        )
    if not request.cron_expression and not request.interval_seconds:
        return OperationResult.fail(
            "VALIDATION_FAILED",
            "Either cron_expression or interval_seconds is required",
            elapsed_ms=timer.elapsed_ms,
        )

    if ctx.dry_run:
        return OperationResult.ok(
            ScheduleDetail(
                name=request.name,
                target_type=request.target_type,
                target_name=request.target_name,
                cron_expression=request.cron_expression,
                interval_seconds=request.interval_seconds,
                enabled=request.enabled,
            ),
            elapsed_ms=timer.elapsed_ms,
        )

    schedule_id = str(uuid.uuid4())
    schedule_name = request.name or request.target_name

    try:
        repo = _sched_repo(ctx)
        repo.create_schedule({
            "id": schedule_id,
            "name": schedule_name,
            "target_type": request.target_type,
            "target_name": request.target_name,
            "cron_expression": request.cron_expression,
            "interval_seconds": request.interval_seconds,
            "enabled": request.enabled,
        })
        ctx.conn.commit()

        return OperationResult.ok(
            ScheduleDetail(
                schedule_id=schedule_id,
                name=schedule_name,
                target_type=request.target_type,
                target_name=request.target_name,
                cron_expression=request.cron_expression,
                interval_seconds=request.interval_seconds,
                enabled=request.enabled,
            ),
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL", f"Failed to create schedule: {exc}", elapsed_ms=timer.elapsed_ms
        )


def update_schedule(
    ctx: OperationContext,
    request: UpdateScheduleRequest,
) -> OperationResult[ScheduleDetail]:
    """Update an existing schedule."""
    timer = start_timer()

    if not request.schedule_id:
        return OperationResult.fail(
            "VALIDATION_FAILED", "schedule_id is required", elapsed_ms=timer.elapsed_ms
        )

    if ctx.dry_run:
        return OperationResult.ok(
            ScheduleDetail(schedule_id=request.schedule_id),
            elapsed_ms=timer.elapsed_ms,
        )

    sets: list[str] = []
    updates_dict: dict[str, Any] = {}

    if request.cron_expression is not None:
        updates_dict["cron_expression"] = request.cron_expression
    if request.interval_seconds is not None:
        updates_dict["interval_seconds"] = request.interval_seconds
    if request.enabled is not None:
        updates_dict["enabled"] = request.enabled
    if request.name is not None:
        updates_dict["name"] = request.name
    if request.target_name is not None:
        updates_dict["target_name"] = request.target_name

    if not updates_dict:
        return OperationResult.fail(
            "VALIDATION_FAILED", "No fields to update", elapsed_ms=timer.elapsed_ms
        )

    try:
        repo = _sched_repo(ctx)
        repo.update_schedule(request.schedule_id, updates_dict)
        ctx.conn.commit()
        return get_schedule(ctx, GetScheduleRequest(schedule_id=request.schedule_id))
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL", f"Failed to update schedule: {exc}", elapsed_ms=timer.elapsed_ms
        )


def delete_schedule(
    ctx: OperationContext,
    request: DeleteScheduleRequest,
) -> OperationResult[None]:
    """Delete a schedule."""
    timer = start_timer()

    if not request.schedule_id:
        return OperationResult.fail(
            "VALIDATION_FAILED", "schedule_id is required", elapsed_ms=timer.elapsed_ms
        )

    if ctx.dry_run:
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)

    try:
        repo = _sched_repo(ctx)
        repo.delete_schedule(request.schedule_id)
        ctx.conn.commit()
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL", f"Failed to delete schedule: {exc}", elapsed_ms=timer.elapsed_ms
        )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _col(row: Any, idx: int, name: str, default: Any = "") -> Any:
    """Extract a column from a row that may be a dict, Row, or tuple."""
    if isinstance(row, dict):
        return row.get(name, default)
    if hasattr(row, "keys"):
        return dict(row).get(name, default)
    try:
        return row[idx]
    except (IndexError, TypeError):
        return default


# ------------------------------------------------------------------ #
# Calculation Dependencies (wires core_calc_dependencies)
# ------------------------------------------------------------------ #


def list_calc_dependencies(
    ctx: OperationContext,
    request: ListCalcDependenciesRequest | None = None,
) -> PagedResult[CalcDependencySummary]:
    """List calculation dependencies.

    Shows which pipelines depend on which upstream data sources,
    enabling dependency graph visualization and cascade invalidation.
    """
    from spine.ops.responses import CalcDependencySummary

    timer = start_timer()
    limit = request.limit if request else 100
    offset = request.offset if request else 0

    try:
        repo = _calc_dep_repo(ctx)
        rows, total = repo.list_deps(
            calc_domain=request.calc_domain if request else None,
            calc_pipeline=request.calc_pipeline if request else None,
            depends_on_domain=request.depends_on_domain if request else None,
            limit=limit,
            offset=offset,
        )

        summaries = [
            CalcDependencySummary(
                id=r.get("id", 0),
                calc_domain=r.get("calc_domain", ""),
                calc_pipeline=r.get("calc_pipeline", ""),
                calc_table=r.get("calc_table"),
                depends_on_domain=r.get("depends_on_domain", ""),
                depends_on_table=r.get("depends_on_table", ""),
                dependency_type=r.get("dependency_type", "REQUIRED"),
                description=r.get("description"),
            )
            for r in rows
        ]

        return PagedResult.from_items(
            summaries,
            total=total,
            limit=limit,
            offset=offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception:
        # Table may not exist
        return PagedResult.from_items([], total=0, elapsed_ms=timer.elapsed_ms)


# ------------------------------------------------------------------ #
# Expected Schedules (wires core_expected_schedules)
# ------------------------------------------------------------------ #


def list_expected_schedules(
    ctx: OperationContext,
    request: ListExpectedSchedulesRequest | None = None,
) -> PagedResult[ExpectedScheduleSummary]:
    """List expected workflow schedules.

    Defines when workflows SHOULD run — used for detecting missed
    runs and SLA breaches.
    """
    from spine.ops.responses import ExpectedScheduleSummary

    timer = start_timer()
    limit = request.limit if request else 50
    offset = request.offset if request else 0

    try:
        repo = _exp_sched_repo(ctx)
        rows, total = repo.list_schedules(
            domain=request.domain if request else None,
            workflow=request.workflow if request else None,
            schedule_type=request.schedule_type if request else None,
            is_active=request.is_active if request else None,
            limit=limit,
            offset=offset,
        )

        summaries = [
            ExpectedScheduleSummary(
                id=r.get("id", 0),
                domain=r.get("domain", ""),
                workflow=r.get("workflow", ""),
                schedule_type=r.get("schedule_type", ""),
                cron_expression=r.get("cron_expression"),
                expected_delay_hours=r.get("expected_delay_hours"),
                preliminary_hours=r.get("preliminary_hours"),
                is_active=bool(r.get("is_active", 1)),
            )
            for r in rows
        ]

        return PagedResult.from_items(
            summaries,
            total=total,
            limit=limit,
            offset=offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception:
        # Table may not exist
        return PagedResult.from_items([], total=0, elapsed_ms=timer.elapsed_ms)


# ------------------------------------------------------------------ #
# Data Readiness (wires core_data_readiness)
# ------------------------------------------------------------------ #


def check_data_readiness(
    ctx: OperationContext,
    request: CheckDataReadinessRequest,
) -> PagedResult[DataReadinessSummary]:
    """Check data readiness certification status.

    Returns readiness records for the given domain/partition,
    showing which criteria have been satisfied.
    """
    import json

    from spine.ops.responses import DataReadinessSummary

    timer = start_timer()

    if not request.domain:
        return PagedResult(
            success=False,
            error=OperationError(code="VALIDATION_FAILED", message="domain is required"),
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        repo = _readiness_repo(ctx)
        rows, total = repo.check_readiness(
            domain=request.domain,
            partition_key=request.partition_key,
            ready_for=request.ready_for,
        )

        summaries = []
        for r in rows:
            blocking_raw = r.get("blocking_issues", "[]")
            try:
                blocking = json.loads(blocking_raw) if blocking_raw else []
            except (json.JSONDecodeError, TypeError):
                blocking = []

            summaries.append(
                DataReadinessSummary(
                    id=r.get("id", 0),
                    domain=r.get("domain", ""),
                    partition_key=r.get("partition_key", ""),
                    is_ready=bool(r.get("is_ready", 0)),
                    ready_for=r.get("ready_for"),
                    all_partitions_present=bool(r.get("all_partitions_present", 0)),
                    all_stages_complete=bool(r.get("all_stages_complete", 0)),
                    no_critical_anomalies=bool(r.get("no_critical_anomalies", 0)),
                    dependencies_current=bool(r.get("dependencies_current", 0)),
                    blocking_issues=blocking,
                    certified_at=r.get("certified_at"),
                )
            )

        return PagedResult.from_items(
            summaries,
            total=total,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=OperationError(code="INTERNAL", message=f"Failed to check readiness: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


# Bring OperationError into scope for use in check_data_readiness
from spine.core.logging import get_logger
from spine.ops.result import OperationError

logger = get_logger(__name__)
