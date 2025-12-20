"""
Typed request objects for operations.

Each dataclass represents the *input* contract for a single operation
function.  Requests carry only validated, transport-agnostic data — no
raw HTTP bodies, no Click params.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ------------------------------------------------------------------ #
# Database operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class DatabaseInitRequest:
    """Request for :func:`spine.ops.database.initialize_database`."""

    include_extensions: bool = False


@dataclass(frozen=True, slots=True)
class PurgeRequest:
    """Request for :func:`spine.ops.database.purge_old_data`."""

    older_than_days: int = 90
    tables: list[str] | None = None  # ``None`` → all purgeable tables


# ------------------------------------------------------------------ #
# Run operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class SubmitRunRequest:
    """Request for :func:`spine.ops.runs.submit_run`.

    Attributes:
        kind: Work type — ``"task"``, ``"pipeline"``, ``"workflow"``.
        name: Handler or workflow name.
        params: Arbitrary runtime parameters.
        idempotency_key: Optional deduplication key.
        priority: Execution priority (``"realtime"``, ``"high"``, ``"normal"``, ``"low"``).
        metadata: Freeform metadata attached to the run.
    """

    kind: str = "task"
    name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    priority: str = "normal"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GetRunEventsRequest:
    """Request for :func:`spine.ops.runs.get_run_events`."""

    run_id: str = ""
    limit: int = 200
    offset: int = 0


@dataclass(frozen=True, slots=True)
class GetRunStepsRequest:
    """Request for :func:`spine.ops.runs.get_run_steps`.

    Returns step-level timing data for workflow runs.
    """

    run_id: str = ""
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ListRunsRequest:
    """Request for :func:`spine.ops.runs.list_runs`.

    Attributes:
        kind: Filter by run kind (``"pipeline"``, ``"workflow"``).
        status: Filter by status name.
        workflow: Filter by workflow name.
        since: Only runs started after this datetime (inclusive).
        until: Only runs started before this datetime (exclusive).
        limit: Maximum items to return.
        offset: Pagination offset.
    """

    kind: str | None = None
    status: str | None = None
    workflow: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class GetRunRequest:
    """Request for :func:`spine.ops.runs.get_run`."""

    run_id: str = ""


@dataclass(frozen=True, slots=True)
class CancelRunRequest:
    """Request for :func:`spine.ops.runs.cancel_run`."""

    run_id: str = ""
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RetryRunRequest:
    """Request for :func:`spine.ops.runs.retry_run`."""

    run_id: str = ""


# ------------------------------------------------------------------ #
# Workflow operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class GetWorkflowRequest:
    """Request for :func:`spine.ops.workflows.get_workflow`."""

    name: str = ""


@dataclass(frozen=True, slots=True)
class RunWorkflowRequest:
    """Request for :func:`spine.ops.workflows.run_workflow`.

    Attributes:
        name: Workflow registered name.
        params: Runtime parameters forwarded to the workflow.
        idempotency_key: Optional key for at-most-once execution.
    """

    name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None


# ------------------------------------------------------------------ #
# Schedule operations  (stubbed — full impl in Phase 3)
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class CreateScheduleRequest:
    """Request for :func:`spine.ops.schedules.create_schedule`."""

    name: str = ""
    target_type: str = "pipeline"
    target_name: str = ""
    cron_expression: str | None = None
    interval_seconds: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class UpdateScheduleRequest:
    """Request for :func:`spine.ops.schedules.update_schedule`."""

    schedule_id: str = ""
    name: str | None = None
    target_name: str | None = None
    cron_expression: str | None = None
    interval_seconds: int | None = None
    enabled: bool | None = None
    params: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class GetScheduleRequest:
    """Request for :func:`spine.ops.schedules.get_schedule`."""

    schedule_id: str = ""


@dataclass(frozen=True, slots=True)
class DeleteScheduleRequest:
    """Request for :func:`spine.ops.schedules.delete_schedule`."""

    schedule_id: str = ""


# ------------------------------------------------------------------ #
# DLQ operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class ListDeadLettersRequest:
    """Request for :func:`spine.ops.dlq.list_dead_letters`."""

    workflow: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ReplayDeadLetterRequest:
    """Request for :func:`spine.ops.dlq.replay_dead_letter`."""

    dead_letter_id: str = ""


# ------------------------------------------------------------------ #
# Quality operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class ListQualityResultsRequest:
    """Request for :func:`spine.ops.quality.list_quality_results`."""

    workflow: str | None = None
    since: datetime | None = None
    limit: int = 50
    offset: int = 0


# ------------------------------------------------------------------ #
# Anomaly operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class ListAnomaliesRequest:
    """Request for :func:`spine.ops.anomalies.list_anomalies`."""

    workflow: str | None = None
    severity: str | None = None
    since: datetime | None = None
    limit: int = 50
    offset: int = 0


# ------------------------------------------------------------------ #
# Alert operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class ListAlertChannelsRequest:
    """Request for :func:`spine.ops.alerts.list_alert_channels`."""

    channel_type: str | None = None
    enabled: bool | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class CreateAlertChannelRequest:
    """Request for :func:`spine.ops.alerts.create_alert_channel`."""

    name: str = ""
    channel_type: str = "slack"  # slack, email, webhook, servicenow, pagerduty
    config: dict[str, Any] = field(default_factory=dict)
    min_severity: str = "ERROR"
    domains: list[str] | None = None
    enabled: bool = True
    throttle_minutes: int = 5


@dataclass(frozen=True, slots=True)
class ListAlertsRequest:
    """Request for :func:`spine.ops.alerts.list_alerts`."""

    severity: str | None = None
    source: str | None = None
    since: datetime | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class CreateAlertRequest:
    """Request for :func:`spine.ops.alerts.create_alert`."""

    severity: str = "ERROR"
    title: str = ""
    message: str = ""
    source: str = ""
    domain: str | None = None
    execution_id: str | None = None
    run_id: str | None = None
    metadata: dict[str, Any] | None = None
    error_category: str | None = None


@dataclass(frozen=True, slots=True)
class ListAlertDeliveriesRequest:
    """Request for :func:`spine.ops.alerts.list_alert_deliveries`."""

    alert_id: str | None = None
    channel_id: str | None = None
    status: str | None = None
    limit: int = 50
    offset: int = 0


# ------------------------------------------------------------------ #
# Source operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class ListSourcesRequest:
    """Request for :func:`spine.ops.sources.list_sources`."""

    source_type: str | None = None
    domain: str | None = None
    enabled: bool | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class CreateSourceRequest:
    """Request for :func:`spine.ops.sources.register_source`."""

    name: str = ""
    source_type: str = "file"  # file, http, database, s3, sftp
    config: dict[str, Any] = field(default_factory=dict)
    domain: str | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ListSourceFetchesRequest:
    """Request for :func:`spine.ops.sources.list_source_fetches`."""

    source_id: str | None = None
    source_name: str | None = None
    status: str | None = None
    since: datetime | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ListDatabaseConnectionsRequest:
    """Request for :func:`spine.ops.sources.list_database_connections`."""

    dialect: str | None = None
    enabled: bool | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class CreateDatabaseConnectionRequest:
    """Request for :func:`spine.ops.sources.register_database_connection`."""

    name: str = ""
    dialect: str = "postgresql"  # postgresql, mysql, sqlite, oracle, db2
    host: str | None = None
    port: int | None = None
    database: str = ""
    username: str | None = None
    password_ref: str | None = None  # Reference to secret, not actual password
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    enabled: bool = True


# ------------------------------------------------------------------ #
# Workflow event operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class ListWorkflowEventsRequest:
    """Request for :func:`spine.ops.workflows.list_workflow_events`."""

    run_id: str
    step_id: str | None = None
    event_type: str | None = None
    limit: int = 100
    offset: int = 0


# ------------------------------------------------------------------ #
# Schedule lock operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class ListScheduleLocksRequest:
    """Request for :func:`spine.ops.locks.list_schedule_locks`."""

    limit: int = 50
    offset: int = 0


# ------------------------------------------------------------------ #
# Scheduler metadata operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class ListCalcDependenciesRequest:
    """Request for :func:`spine.ops.schedules.list_calc_dependencies`."""

    calc_domain: str | None = None
    calc_pipeline: str | None = None
    depends_on_domain: str | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ListExpectedSchedulesRequest:
    """Request for :func:`spine.ops.schedules.list_expected_schedules`."""

    domain: str | None = None
    workflow: str | None = None
    schedule_type: str | None = None
    is_active: bool | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class CheckDataReadinessRequest:
    """Request for :func:`spine.ops.schedules.check_data_readiness`."""

    domain: str
    partition_key: str | None = None
    ready_for: str | None = None


# ------------------------------------------------------------------ #
# Workflow data operations
# ------------------------------------------------------------------ #


@dataclass(frozen=True, slots=True)
class ListManifestEntriesRequest:
    """Request for :func:`spine.ops.processing.list_manifest_entries`."""

    domain: str | None = None
    partition_key: str | None = None
    stage: str | None = None
    since: datetime | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ListRejectsRequest:
    """Request for :func:`spine.ops.processing.list_rejects`."""

    domain: str | None = None
    partition_key: str | None = None
    stage: str | None = None
    reason_code: str | None = None
    execution_id: str | None = None
    since: datetime | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ListWorkItemsRequest:
    """Request for :func:`spine.ops.processing.list_work_items`."""

    domain: str | None = None
    workflow: str | None = None
    state: str | None = None  # PENDING, RUNNING, COMPLETE, FAILED, RETRY_WAIT, CANCELLED
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ClaimWorkItemRequest:
    """Request for :func:`spine.ops.processing.claim_work_item`."""

    item_id: int
    worker_id: str
