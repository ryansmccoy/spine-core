"""Core framework table models (00_core.sql).

Manifesto:
    The fundamental spine-core tables (executions, manifest, rejects,
    quality, anomalies, work items, dead letters, locks, dependencies,
    schedules, data readiness) each need a typed dataclass so the ops
    and API layers work with structured objects instead of raw dicts.

Models for the fundamental spine-core tables: executions, manifest,
rejects, quality, anomalies, work items, dead letters, concurrency
locks, calculation dependencies, expected schedules, and data readiness.

Tags:
    spine-core, models, dataclasses, core-tables, schema-mapping

Doc-Types:
    api-reference, data-model
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# _migrations
# ---------------------------------------------------------------------------


@dataclass
class MigrationRecord:
    """A row in the ``_migrations`` tracking table."""

    id: int | None = None
    filename: str = ""
    applied_at: str | None = None


# ---------------------------------------------------------------------------
# core_executions
# ---------------------------------------------------------------------------


@dataclass
class Execution:
    """Workflow execution ledger row (``core_executions``)."""

    id: str = ""
    workflow: str = ""
    params: str | None = "{}"  # JSON parameters
    lane: str = "normal"
    trigger_source: str = "api"
    logical_key: str | None = None
    status: str = "pending"
    parent_execution_id: str | None = None
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    result: str | None = None
    error: str | None = None
    retry_count: int = 0
    idempotency_key: str | None = None


# ---------------------------------------------------------------------------
# core_execution_events
# ---------------------------------------------------------------------------


@dataclass
class ExecutionEvent:
    """Immutable event log row for execution lifecycle (``core_execution_events``)."""

    id: str = ""
    execution_id: str = ""
    event_type: str = ""
    timestamp: str = ""
    data: str = "{}"  # JSON payload


# ---------------------------------------------------------------------------
# core_manifest
# ---------------------------------------------------------------------------


@dataclass
class ManifestEntry:
    """Stage tracking row (``core_manifest``).

    Note: This complements the existing ``ManifestRow`` class in
    ``spine.core.manifest`` — that class has behavior (``__repr__``),
    this is a pure data model for serialization.
    """

    domain: str = ""
    partition_key: str = ""  # JSON logical key
    stage: str = ""
    stage_rank: int | None = None
    row_count: int | None = None
    metrics_json: str | None = None
    execution_id: str | None = None
    batch_id: str | None = None
    updated_at: str = ""


# ---------------------------------------------------------------------------
# core_rejects
# ---------------------------------------------------------------------------


@dataclass
class RejectRecord:
    """Rejected record row (``core_rejects``).

    Note: Complements the existing ``Reject`` dataclass in
    ``spine.core.rejects`` which is used for writing. This model
    includes all persisted fields (domain, execution_id, etc.).
    """

    id: int | None = None
    domain: str = ""
    partition_key: str = ""
    stage: str = ""
    reason_code: str = ""
    reason_detail: str | None = None
    raw_json: str | None = None
    record_key: str | None = None
    source_locator: str | None = None
    line_number: int | None = None
    execution_id: str = ""
    batch_id: str | None = None
    created_at: str = ""


# ---------------------------------------------------------------------------
# core_quality
# ---------------------------------------------------------------------------


@dataclass
class QualityRecord:
    """Quality check result row (``core_quality``)."""

    id: int | None = None
    domain: str = ""
    partition_key: str = ""
    check_name: str = ""
    category: str = ""  # INTEGRITY, COMPLETENESS, BUSINESS_RULE
    status: str = ""  # PASS, WARN, FAIL
    message: str | None = None
    actual_value: str | None = None
    expected_value: str | None = None
    details_json: str | None = None
    execution_id: str = ""
    batch_id: str | None = None
    created_at: str = ""


# ---------------------------------------------------------------------------
# core_anomalies
# ---------------------------------------------------------------------------


@dataclass
class AnomalyRecord:
    """Anomaly record row (``core_anomalies``)."""

    id: int | None = None
    domain: str = ""
    workflow: str | None = None
    partition_key: str | None = None
    stage: str | None = None
    severity: str = ""  # DEBUG, INFO, WARN, ERROR, CRITICAL
    category: str = ""  # QUALITY_GATE, NETWORK, DATA_QUALITY, etc.
    message: str = ""
    details_json: str | None = None
    affected_records: int | None = None
    sample_records: str | None = None
    execution_id: str | None = None
    batch_id: str | None = None
    capture_id: str | None = None
    detected_at: str = ""
    resolved_at: str | None = None
    resolution_note: str | None = None
    created_at: str | None = None


# ---------------------------------------------------------------------------
# core_work_items
# ---------------------------------------------------------------------------


@dataclass
class WorkItem:
    """Scheduled work item row (``core_work_items``)."""

    id: int | None = None
    domain: str = ""
    workflow: str = ""
    partition_key: str = ""
    params_json: str | None = None
    desired_at: str = ""
    priority: int = 100
    state: str = "PENDING"
    attempt_count: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    last_error_at: str | None = None
    next_attempt_at: str | None = None
    current_execution_id: str | None = None
    latest_execution_id: str | None = None
    locked_by: str | None = None
    locked_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None


# ---------------------------------------------------------------------------
# core_dead_letters
# ---------------------------------------------------------------------------


@dataclass
class DeadLetter:
    """Dead letter queue row (``core_dead_letters``)."""

    id: str = ""
    execution_id: str = ""
    workflow: str = ""
    params: str = "{}"  # JSON parameters
    error: str = ""
    retry_count: int = 0
    max_retries: int = 3
    created_at: str = ""
    last_retry_at: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None


# ---------------------------------------------------------------------------
# core_concurrency_locks
# ---------------------------------------------------------------------------


@dataclass
class ConcurrencyLock:
    """Concurrency lock row (``core_concurrency_locks``)."""

    lock_key: str = ""
    execution_id: str = ""
    acquired_at: str = ""
    expires_at: str = ""


# ---------------------------------------------------------------------------
# core_calc_dependencies
# ---------------------------------------------------------------------------


@dataclass
class CalcDependency:
    """Calculation dependency row (``core_calc_dependencies``)."""

    id: int | None = None
    calc_domain: str = ""
    calc_operation: str = ""
    calc_table: str | None = None
    depends_on_domain: str = ""
    depends_on_table: str = ""
    dependency_type: str = ""  # REQUIRED, OPTIONAL, REFERENCE
    description: str | None = None
    created_at: str | None = None


# ---------------------------------------------------------------------------
# core_expected_schedules
# ---------------------------------------------------------------------------


@dataclass
class ExpectedSchedule:
    """Expected schedule specification (``core_expected_schedules``)."""

    id: int | None = None
    domain: str = ""
    workflow: str = ""
    schedule_type: str = ""  # WEEKLY, DAILY, MONTHLY, ANNUAL, TRIGGERED
    cron_expression: str | None = None
    partition_template: str = ""
    partition_values: str | None = None
    expected_delay_hours: int | None = None
    preliminary_hours: int | None = None
    description: str | None = None
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# core_data_readiness
# ---------------------------------------------------------------------------


@dataclass
class DataReadiness:
    """Data readiness certification row (``core_data_readiness``)."""

    id: int | None = None
    domain: str = ""
    partition_key: str = ""
    is_ready: bool = False
    ready_for: str | None = None  # trading, compliance, research
    all_partitions_present: bool = False
    all_stages_complete: bool = False
    no_critical_anomalies: bool = False
    dependencies_current: bool = False
    age_exceeds_preliminary: bool = False
    blocking_issues: str | None = None
    certified_at: str | None = None
    certified_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
