"""Scheduler table models (03_scheduler.sql).

Manifesto:
    Schedule definitions, execution history, and distributed locks
    need typed dataclass representations so the scheduling service
    and API can work with structured objects.

Models for cron-based operation scheduling: schedule definitions,
execution history, and distributed locks.

Tags:
    spine-core, models, scheduling, dataclasses, cron, schema-mapping

Doc-Types:
    api-reference, data-model
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# core_schedules
# ---------------------------------------------------------------------------


@dataclass
class Schedule:
    """Schedule definition row (``core_schedules``)."""

    id: str = ""
    name: str = ""
    target_type: str = "operation"  # operation, workflow
    target_name: str = ""
    params: str | None = None  # JSON default parameters
    schedule_type: str = "cron"  # cron, interval, date
    cron_expression: str | None = None
    interval_seconds: int | None = None
    run_at: str | None = None
    timezone: str = "UTC"
    enabled: bool = True
    max_instances: int = 1
    misfire_grace_seconds: int = 60
    last_run_at: str | None = None
    next_run_at: str | None = None
    last_run_status: str | None = None
    created_at: str = ""
    updated_at: str = ""
    created_by: str | None = None
    version: int = 1


# ---------------------------------------------------------------------------
# core_schedule_runs
# ---------------------------------------------------------------------------


@dataclass
class ScheduleRun:
    """Scheduled execution history row (``core_schedule_runs``)."""

    id: str = ""
    schedule_id: str = ""
    schedule_name: str = ""
    scheduled_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED, MISSED
    run_id: str | None = None
    execution_id: str | None = None
    error: str | None = None
    skip_reason: str | None = None
    created_at: str = ""


# ---------------------------------------------------------------------------
# core_schedule_locks
# ---------------------------------------------------------------------------


@dataclass
class ScheduleLock:
    """Distributed scheduler lock row (``core_schedule_locks``)."""

    schedule_id: str = ""
    locked_by: str = ""
    locked_at: str = ""
    expires_at: str = ""
