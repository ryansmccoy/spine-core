"""Scheduling table definitions — schedules, runs, locks.

Tags:
    spine-core, orm, sqlalchemy, tables, scheduling

Doc-Types:
    api-reference, data-model
"""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spine.core.orm.base import SpineBase

_NOW = text("(datetime('now'))")


class ScheduleTable(SpineBase):
    __tablename__ = "core_schedules"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    target_type: Mapped[str] = mapped_column(
        Text, default="operation", nullable=False
    )
    target_name: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict | None] = mapped_column(JSON)
    schedule_type: Mapped[str] = mapped_column(Text, default="cron", nullable=False)
    cron_expression: Mapped[str | None] = mapped_column(Text)
    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    run_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    timezone: Mapped[str] = mapped_column(Text, default="UTC", nullable=False)
    enabled: Mapped[bool] = mapped_column(Integer, default=True, nullable=False)
    max_instances: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    misfire_grace_seconds: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False
    )
    last_run_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    next_run_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    last_run_status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    created_by: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # --- relationships ---
    runs: Mapped[list[ScheduleRunTable]] = relationship(
        "ScheduleRunTable", backref="schedule"
    )
    lock: Mapped[ScheduleLockTable | None] = relationship(
        "ScheduleLockTable", backref="schedule", uselist=False
    )


class ScheduleRunTable(SpineBase):
    __tablename__ = "core_schedule_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    schedule_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_schedules.id"), nullable=False
    )
    schedule_name: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(Text, default="PENDING", nullable=False)
    run_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_workflow_runs.run_id")
    )
    execution_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_executions.id")
    )
    error: Mapped[str | None] = mapped_column(Text)
    skip_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )


class ScheduleLockTable(SpineBase):
    __tablename__ = "core_schedule_locks"

    schedule_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_schedules.id"), primary_key=True
    )
    locked_by: Mapped[str] = mapped_column(Text, nullable=False)
    locked_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
