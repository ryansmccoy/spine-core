"""
Typed response objects for operations.

Each dataclass represents the *output* of a single operation beyond the
generic :class:`OperationResult` envelope.  Responses carry only domain
data — no HTTP status codes, no CLI formatting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ------------------------------------------------------------------ #
# Database responses
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class DatabaseInitResult:
    """Result payload for :func:`spine.ops.database.initialize_database`."""

    tables_created: list[str]
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class TableCount:
    """Row count for a single table."""

    table: str
    count: int


@dataclass(frozen=True, slots=True)
class PurgeResult:
    """Result payload for :func:`spine.ops.database.purge_old_data`."""

    rows_deleted: int
    tables_purged: list[str]
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    """Database health for :func:`spine.ops.database.check_database_health`."""

    connected: bool
    backend: str = "unknown"  # "sqlite", "postgresql"
    table_count: int = 0
    latency_ms: float = 0.0


# ------------------------------------------------------------------ #
# Run responses
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class RunSummary:
    """Compact run representation for list views."""

    run_id: str
    workflow: str | None = None
    status: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = None


@dataclass(slots=True)
class RunDetail:
    """Full run representation (single-item view)."""

    run_id: str
    workflow: str | None = None
    status: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RunAccepted:
    """Returned when a run is successfully submitted."""

    run_id: str | None = None
    dry_run: bool = False
    would_execute: bool = True


@dataclass(slots=True)
class RunEvent:
    """A single event from a run's event-sourced history."""

    event_id: str = ""
    run_id: str = ""
    event_type: str = ""
    timestamp: datetime | None = None
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass(slots=True)
class StepTiming:
    """Step-level timing data for workflow runs.

    Used by the Step Timing API to expose execution details for each
    step in a workflow run.
    """

    step_id: str = ""
    run_id: str = ""
    step_name: str = ""
    step_type: str = ""  # pipeline, task, condition, parallel
    step_order: int = 0
    status: str = ""  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    row_count: int | None = None
    attempt: int = 1
    max_attempts: int = 1
    error: str | None = None
    error_category: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------ #
# Workflow responses
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class WorkflowSummary:
    """Compact workflow representation for list views."""

    name: str
    step_count: int = 0
    description: str = ""


@dataclass(slots=True)
class WorkflowDetail:
    """Full workflow representation (single-item view)."""

    name: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------ #
# Schedule responses  (stubbed — full impl in Phase 3)
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class ScheduleSummary:
    """Compact schedule representation."""

    schedule_id: str = ""
    name: str = ""
    target_type: str = "pipeline"
    target_name: str = ""
    cron_expression: str | None = None
    interval_seconds: int | None = None
    enabled: bool = True
    next_run_at: datetime | None = None


@dataclass(slots=True)
class ScheduleDetail:
    """Full schedule representation."""

    schedule_id: str = ""
    name: str = ""
    target_type: str = "pipeline"
    target_name: str = ""
    cron_expression: str | None = None
    interval_seconds: int | None = None
    enabled: bool = True
    params: dict[str, Any] = field(default_factory=dict)
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    created_at: datetime | None = None
    version: int = 1


# ------------------------------------------------------------------ #
# Health / capabilities responses
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class Capabilities:
    """Runtime capability introspection."""

    tier: str = "standard"
    sync_execution: bool = True
    async_execution: bool = True
    scheduling: bool = True
    rate_limiting: bool = True
    execution_history: bool = True
    dlq: bool = True


@dataclass(slots=True)
class HealthStatus:
    """Aggregate health status."""

    status: str = "healthy"  # "healthy", "degraded", "unhealthy"
    database: DatabaseHealth | None = None
    checks: dict[str, str] = field(default_factory=dict)
    version: str = ""


# ------------------------------------------------------------------ #
# DLQ responses
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class DeadLetterSummary:
    """Compact dead-letter representation."""

    id: str = ""
    workflow: str = ""
    error: str = ""
    created_at: datetime | None = None
    replay_count: int = 0


# ------------------------------------------------------------------ #
# Quality responses
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class QualityResultSummary:
    """Compact quality result representation."""

    workflow: str = ""
    checks_passed: int = 0
    checks_failed: int = 0
    score: float = 0.0
    run_at: datetime | None = None


# ------------------------------------------------------------------ #
# Anomaly responses
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class AnomalySummary:
    """Compact anomaly representation."""

    id: str = ""
    workflow: str = ""
    metric: str = ""
    severity: str = ""
    value: float = 0.0
    threshold: float = 0.0
    detected_at: datetime | None = None


# ------------------------------------------------------------------ #
# Alert responses
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class AlertChannelSummary:
    """Compact alert channel representation."""

    id: str = ""
    name: str = ""
    channel_type: str = ""
    min_severity: str = "ERROR"
    enabled: bool = True
    consecutive_failures: int = 0
    created_at: datetime | str | None = None


@dataclass(slots=True)
class AlertChannelDetail:
    """Full alert channel representation."""

    id: str = ""
    name: str = ""
    channel_type: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    min_severity: str = "ERROR"
    domains: list[str] | None = None
    enabled: bool = True
    throttle_minutes: int = 5
    last_success_at: datetime | str | None = None
    last_failure_at: datetime | str | None = None
    consecutive_failures: int = 0
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None


@dataclass(slots=True)
class AlertSummary:
    """Compact alert representation."""

    id: str = ""
    severity: str = ""
    title: str = ""
    message: str = ""
    source: str = ""
    domain: str | None = None
    created_at: datetime | str | None = None


@dataclass(slots=True)
class AlertDeliverySummary:
    """Compact alert delivery representation."""

    id: str = ""
    alert_id: str = ""
    channel_id: str = ""
    channel_name: str = ""
    status: str = ""
    attempted_at: datetime | str | None = None
    delivered_at: datetime | str | None = None
    error: str | None = None
    attempt: int = 1


# ------------------------------------------------------------------ #
# Source responses
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class SourceSummary:
    """Compact source representation."""

    id: str = ""
    name: str = ""
    source_type: str = ""
    domain: str | None = None
    enabled: bool = True
    created_at: datetime | str | None = None


@dataclass(slots=True)
class SourceDetail:
    """Full source representation."""

    id: str = ""
    name: str = ""
    source_type: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    domain: str | None = None
    enabled: bool = True
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None


@dataclass(slots=True)
class SourceFetchSummary:
    """Compact source fetch representation."""

    id: str = ""
    source_id: str | None = None
    source_name: str = ""
    source_type: str = ""
    source_locator: str = ""
    status: str = ""
    record_count: int | None = None
    byte_count: int | None = None
    started_at: datetime | str | None = None
    duration_ms: int | None = None
    error: str | None = None


@dataclass(slots=True)
class SourceCacheSummary:
    """Compact source cache entry representation."""

    cache_key: str = ""
    source_id: str | None = None
    source_type: str = ""
    source_locator: str = ""
    content_hash: str = ""
    content_size: int = 0
    fetched_at: datetime | str | None = None
    expires_at: datetime | str | None = None


@dataclass(slots=True)
class DatabaseConnectionSummary:
    """Compact database connection representation."""

    id: str = ""
    name: str = ""
    dialect: str = ""
    host: str | None = None
    port: int | None = None
    database: str = ""
    enabled: bool = True
    last_connected_at: datetime | str | None = None
    last_error: str | None = None
    created_at: datetime | str | None = None


# ------------------------------------------------------------------ #
# Workflow events responses
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class WorkflowEventSummary:
    """Workflow lifecycle event."""

    id: int = 0
    run_id: str = ""
    step_id: str | None = None
    event_type: str = ""
    timestamp: datetime | str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------ #
# Schedule lock responses
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class ScheduleLockSummary:
    """Schedule-level distributed lock."""

    schedule_id: str = ""
    locked_by: str = ""
    locked_at: datetime | str | None = None
    expires_at: datetime | str | None = None


# ------------------------------------------------------------------ #
# Scheduler metadata responses
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class CalcDependencySummary:
    """Calculation dependency relationship."""

    id: int = 0
    calc_domain: str = ""
    calc_pipeline: str = ""
    calc_table: str | None = None
    depends_on_domain: str = ""
    depends_on_table: str = ""
    dependency_type: str = "REQUIRED"
    description: str | None = None


@dataclass(slots=True)
class ExpectedScheduleSummary:
    """Expected workflow schedule (for SLA tracking)."""

    id: int = 0
    domain: str = ""
    workflow: str = ""
    schedule_type: str = ""
    cron_expression: str | None = None
    expected_delay_hours: int | None = None
    preliminary_hours: int | None = None
    is_active: bool = True


@dataclass(slots=True)
class DataReadinessSummary:
    """Data readiness certification status."""

    id: int = 0
    domain: str = ""
    partition_key: str = ""
    is_ready: bool = False
    ready_for: str | None = None
    all_partitions_present: bool = False
    all_stages_complete: bool = False
    no_critical_anomalies: bool = False
    dependencies_current: bool = False
    blocking_issues: list[str] = field(default_factory=list)
    certified_at: datetime | str | None = None


# ------------------------------------------------------------------ #
# Workflow data responses
# ------------------------------------------------------------------ #


@dataclass(slots=True)
class ManifestEntrySummary:
    """Workflow manifest entry (stage completion status)."""

    domain: str = ""
    partition_key: str = ""
    stage: str = ""
    stage_rank: int | None = None
    row_count: int | None = None
    execution_id: str | None = None
    batch_id: str | None = None
    updated_at: datetime | str | None = None


@dataclass(slots=True)
class RejectSummary:
    """Rejected record from workflow processing."""

    domain: str = ""
    partition_key: str = ""
    stage: str = ""
    reason_code: str = ""
    reason_detail: str | None = None
    record_key: str | None = None
    source_locator: str | None = None
    line_number: int | None = None
    execution_id: str = ""
    created_at: datetime | str | None = None


@dataclass(slots=True)
class WorkItemSummary:
    """Scheduled work item (job queue entry)."""

    id: int = 0
    domain: str = ""
    workflow: str = ""
    partition_key: str = ""
    state: str = "PENDING"
    priority: int = 100
    desired_at: datetime | str | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    locked_by: str | None = None
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None
