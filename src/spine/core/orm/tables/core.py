"""Core table definitions — migrations, executions, processing, anomalies, etc.

Tags:
    spine-core, orm, sqlalchemy, tables, core

Doc-Types:
    api-reference, data-model
"""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spine.core.orm.base import SpineBase

_NOW = text("(datetime('now'))")


class MigrationTable(SpineBase):
    __tablename__ = "_migrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    applied_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )


class ExecutionTable(SpineBase):
    __tablename__ = "core_executions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    workflow: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict | None] = mapped_column(JSON, default=None)
    lane: Mapped[str] = mapped_column(Text, default="normal", nullable=False)
    trigger_source: Mapped[str] = mapped_column(Text, default="api", nullable=False)
    logical_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    parent_execution_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_executions.id"), default=None
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    result: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)

    # --- relationships ---
    parent: Mapped[ExecutionTable | None] = relationship(
        "ExecutionTable", remote_side="ExecutionTable.id", foreign_keys=[parent_execution_id]
    )
    events: Mapped[list[ExecutionEventTable]] = relationship(
        "ExecutionEventTable", back_populates="execution", cascade="all, delete-orphan"
    )


class ExecutionEventTable(SpineBase):
    __tablename__ = "core_execution_events"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    execution_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("core_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    data: Mapped[dict | None] = mapped_column(JSON, server_default=text("'{}'"))

    # --- relationships ---
    execution: Mapped[ExecutionTable] = relationship(
        "ExecutionTable", back_populates="events"
    )


class ManifestTable(SpineBase):
    __tablename__ = "core_manifest"

    domain: Mapped[str] = mapped_column(Text, primary_key=True)
    partition_key: Mapped[str] = mapped_column(Text, primary_key=True)
    stage: Mapped[str] = mapped_column(Text, primary_key=True)
    stage_rank: Mapped[int | None] = mapped_column(Integer)
    row_count: Mapped[int | None] = mapped_column(Integer)
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    execution_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_executions.id")
    )
    batch_id: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)


class RejectTable(SpineBase):
    __tablename__ = "core_rejects"

    rowid: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, name="rowid"
    )
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    partition_key: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    reason_detail: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict | None] = mapped_column(JSON)
    record_key: Mapped[str | None] = mapped_column(Text)
    source_locator: Mapped[str | None] = mapped_column(Text)
    line_number: Mapped[int | None] = mapped_column(Integer)
    execution_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_executions.id"), nullable=False
    )
    batch_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)


class QualityTable(SpineBase):
    __tablename__ = "core_quality"

    rowid: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, name="rowid"
    )
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    partition_key: Mapped[str] = mapped_column(Text, nullable=False)
    check_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    actual_value: Mapped[str | None] = mapped_column(Text)
    expected_value: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[dict | None] = mapped_column(JSON)
    execution_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_executions.id"), nullable=False
    )
    batch_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)


class AnomalyTable(SpineBase):
    __tablename__ = "core_anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    workflow: Mapped[str | None] = mapped_column(Text)
    partition_key: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict | None] = mapped_column(JSON)
    affected_records: Mapped[int | None] = mapped_column(Integer)
    sample_records: Mapped[list | None] = mapped_column(JSON)
    execution_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_executions.id")
    )
    batch_id: Mapped[str | None] = mapped_column(Text)
    capture_id: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=_NOW
    )


class WorkItemTable(SpineBase):
    __tablename__ = "core_work_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    workflow: Mapped[str] = mapped_column(Text, nullable=False)
    partition_key: Mapped[str] = mapped_column(Text, nullable=False)
    params_json: Mapped[dict | None] = mapped_column(JSON)
    desired_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    state: Mapped[str] = mapped_column(Text, default="PENDING", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    next_attempt_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    current_execution_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_executions.id")
    )
    latest_execution_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_executions.id")
    )
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=_NOW
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)


class DeadLetterTable(SpineBase):
    __tablename__ = "core_dead_letters"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    execution_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_executions.id"), nullable=False
    )
    workflow: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict | None] = mapped_column(JSON, server_default=text("'{}'"))
    error: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    last_retry_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    resolved_by: Mapped[str | None] = mapped_column(Text)


class ConcurrencyLockTable(SpineBase):
    __tablename__ = "core_concurrency_locks"

    lock_key: Mapped[str] = mapped_column(Text, primary_key=True)
    execution_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_executions.id"), nullable=False
    )
    acquired_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)


class CalcDependencyTable(SpineBase):
    __tablename__ = "core_calc_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    calc_domain: Mapped[str] = mapped_column(Text, nullable=False)
    calc_operation: Mapped[str] = mapped_column(Text, nullable=False)
    calc_table: Mapped[str | None] = mapped_column(Text)
    depends_on_domain: Mapped[str] = mapped_column(Text, nullable=False)
    depends_on_table: Mapped[str] = mapped_column(Text, nullable=False)
    dependency_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=_NOW
    )


class ExpectedScheduleTable(SpineBase):
    __tablename__ = "core_expected_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    workflow: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_type: Mapped[str] = mapped_column(Text, nullable=False)
    cron_expression: Mapped[str | None] = mapped_column(Text)
    partition_template: Mapped[str] = mapped_column(Text, nullable=False)
    partition_values: Mapped[dict | None] = mapped_column(JSON)
    expected_delay_hours: Mapped[int | None] = mapped_column(Integer)
    preliminary_hours: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Integer, default=True, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=_NOW
    )


class DataReadinessTable(SpineBase):
    __tablename__ = "core_data_readiness"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    partition_key: Mapped[str] = mapped_column(Text, nullable=False)
    is_ready: Mapped[bool] = mapped_column(Integer, default=False, nullable=False)
    ready_for: Mapped[str | None] = mapped_column(Text)
    all_partitions_present: Mapped[bool] = mapped_column(
        Integer, default=False, nullable=False
    )
    all_stages_complete: Mapped[bool] = mapped_column(
        Integer, default=False, nullable=False
    )
    no_critical_anomalies: Mapped[bool] = mapped_column(
        Integer, default=False, nullable=False
    )
    dependencies_current: Mapped[bool] = mapped_column(
        Integer, default=False, nullable=False
    )
    age_exceeds_preliminary: Mapped[bool] = mapped_column(
        Integer, default=False, nullable=False
    )
    blocking_issues: Mapped[list | None] = mapped_column(JSON)
    certified_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    certified_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=_NOW
    )
