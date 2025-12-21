"""Workflow history table definitions — runs, steps, events.

Tags:
    spine-core, orm, sqlalchemy, tables, workflow

Doc-Types:
    api-reference, data-model
"""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spine.core.orm.base import SpineBase

_NOW = text("(datetime('now'))")


class WorkflowRunTable(SpineBase):
    __tablename__ = "core_workflow_runs"

    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    workflow_name: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text)
    partition_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="PENDING", nullable=False)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    params: Mapped[dict | None] = mapped_column(JSON)
    outputs: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    error_category: Mapped[str | None] = mapped_column(Text)
    error_retryable: Mapped[bool | None] = mapped_column(Integer)
    total_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    triggered_by: Mapped[str] = mapped_column(
        Text, default="manual", nullable=False
    )
    parent_run_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_workflow_runs.run_id")
    )
    schedule_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_schedules.id")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    created_by: Mapped[str | None] = mapped_column(Text)
    capture_id: Mapped[str | None] = mapped_column(Text)

    # --- relationships ---
    steps: Mapped[list[WorkflowStepTable]] = relationship(
        "WorkflowStepTable", backref="workflow_run",
        foreign_keys="WorkflowStepTable.run_id",
    )
    events: Mapped[list[WorkflowEventTable]] = relationship(
        "WorkflowEventTable", backref="workflow_run",
        foreign_keys="WorkflowEventTable.run_id",
    )


class WorkflowStepTable(SpineBase):
    __tablename__ = "core_workflow_steps"

    step_id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_workflow_runs.run_id"), nullable=False
    )
    step_name: Mapped[str] = mapped_column(Text, nullable=False)
    step_type: Mapped[str] = mapped_column(Text, nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="PENDING", nullable=False)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    params: Mapped[dict | None] = mapped_column(JSON)
    outputs: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    error_category: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    execution_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_executions.id")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )


class WorkflowEventTable(SpineBase):
    __tablename__ = "core_workflow_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_workflow_runs.run_id"), nullable=False
    )
    step_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_workflow_steps.step_id")
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    payload: Mapped[dict | None] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
