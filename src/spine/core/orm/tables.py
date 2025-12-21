"""SQLAlchemy 2.0 ORM table definitions for spine-core.

Manifesto:
    Every ``CREATE TABLE`` in ``spine.core.schema/*.sql`` has a corresponding
    ``Mapped`` class here so the ORM and raw-SQL layers share the same
    schema.  This is the single authoritative Python-side representation
    of spine-core's database structure.

Every ``CREATE TABLE`` in ``spine.core.schema/*.sql`` has a corresponding
``Mapped`` class here.  Column types are aligned with the SQL DDL:

* ``*_at`` columns -> ``DateTime``
* ``*_json`` / ``params`` / ``spec`` / ``data`` / ``outputs`` / ``metrics`` /
  ``payload`` / ``tags`` -> ``JSON``
* ``is_*`` / ``enabled`` / ``error_retryable`` -> ``Boolean``
  (stored as ``Integer`` on SQLite via ``type_annotation_map``)
* ``ForeignKey`` declared where the SQL DDL has ``FOREIGN KEY``

Tags:
    spine-core, orm, sqlalchemy, tables, schema-mapping, 30-tables

Doc-Types:
    api-reference, data-model

Usage::

    from spine.core.orm import SpineBase
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///spine.db")
    SpineBase.metadata.create_all(engine)
"""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spine.core.orm.base import SpineBase

# Default expression for "now" -- SQLite syntax.  Production DDL uses
# dialect-appropriate NOW() / CURRENT_TIMESTAMP via per-dialect schema files.
_NOW = text("(datetime('now'))")


# =============================================================================
# 00_core.sql
# =============================================================================


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


# =============================================================================
# 02_workflow_history.sql
# =============================================================================


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


# =============================================================================
# 03_scheduler.sql
# =============================================================================


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


# =============================================================================
# 04_alerting.sql
# =============================================================================


class AlertChannelTable(SpineBase):
    __tablename__ = "core_alert_channels"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    channel_type: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    min_severity: Mapped[str] = mapped_column(
        Text, default="ERROR", nullable=False
    )
    domains: Mapped[list | None] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Integer, default=True, nullable=False)
    throttle_minutes: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False
    )
    last_success_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    last_failure_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    created_by: Mapped[str | None] = mapped_column(Text)


class AlertTable(SpineBase):
    __tablename__ = "core_alerts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text)
    execution_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_executions.id")
    )
    run_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_workflow_runs.run_id")
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    error_category: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    dedup_key: Mapped[str | None] = mapped_column(Text)
    capture_id: Mapped[str | None] = mapped_column(Text)

    # --- relationships ---
    deliveries: Mapped[list[AlertDeliveryTable]] = relationship(
        "AlertDeliveryTable", backref="alert"
    )


class AlertDeliveryTable(SpineBase):
    __tablename__ = "core_alert_deliveries"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    alert_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_alerts.id"), nullable=False
    )
    channel_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_alert_channels.id"), nullable=False
    )
    channel_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="PENDING", nullable=False)
    attempted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    response_json: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_retry_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )


class AlertThrottleTable(SpineBase):
    __tablename__ = "core_alert_throttle"

    dedup_key: Mapped[str] = mapped_column(Text, primary_key=True)
    last_sent_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    send_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)


# =============================================================================
# 05_sources.sql
# =============================================================================


class SourceTable(SpineBase):
    __tablename__ = "core_sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Integer, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    created_by: Mapped[str | None] = mapped_column(Text)

    # --- relationships ---
    fetches: Mapped[list[SourceFetchTable]] = relationship(
        "SourceFetchTable", backref="source"
    )
    cache_entries: Mapped[list[SourceCacheTable]] = relationship(
        "SourceCacheTable", backref="source"
    )


class SourceFetchTable(SpineBase):
    __tablename__ = "core_source_fetches"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_sources.id")
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    record_count: Mapped[int | None] = mapped_column(Integer)
    byte_count: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    error_category: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    execution_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_executions.id")
    )
    run_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_workflow_runs.run_id")
    )
    capture_id: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )


class SourceCacheTable(SpineBase):
    __tablename__ = "core_source_cache"

    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_sources.id")
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    content_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_path: Mapped[str | None] = mapped_column(Text)
    # content_blob omitted -- binary handled at DB layer
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    last_accessed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)


class DatabaseConnectionTable(SpineBase):
    __tablename__ = "core_database_connections"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    dialect: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str | None] = mapped_column(Text)
    port: Mapped[int | None] = mapped_column(Integer)
    database: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str | None] = mapped_column(Text)
    password_ref: Mapped[str | None] = mapped_column(Text)
    pool_size: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_overflow: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    pool_timeout: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    enabled: Mapped[bool] = mapped_column(Integer, default=True, nullable=False)
    last_connected_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    created_by: Mapped[str | None] = mapped_column(Text)
