"""
Domain-specific Pydantic schemas for the API layer.

These mirror the ops-layer dataclasses but as Pydantic models so they
get full JSON serialisation, OpenAPI schema generation, and validation.
We keep them intentionally thin — the real types live in ``spine.ops.responses``.

Manifesto:
    Domain-specific schemas keep validation close to the business
    rules so the API rejects invalid data before it hits the ops layer.

Tags:
    spine-core, api, schemas, domain-models, validation

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Status Enums (documented) ────────────────────────────────────────────

RunStatus = Literal["pending", "running", "completed", "failed", "cancelled", "dead_lettered"]
"""
Run execution status values:

- ``pending``: Queued, awaiting worker pickup
- ``running``: Currently executing
- ``completed``: Finished successfully
- ``failed``: Terminated with error (may be retryable)
- ``cancelled``: Manually cancelled by user/operator
- ``dead_lettered``: Moved to DLQ after retry exhaustion
"""

AnomalySeverity = Literal["info", "warning", "critical"]
"""
Anomaly severity levels:

- ``info``: Informational, no action required
- ``warning``: Attention recommended, non-blocking
- ``critical``: Immediate action required
"""


# ── Database ─────────────────────────────────────────────────────────────


class DatabaseInitSchema(BaseModel):
    """Result of database initialization.

    UI Hints:
        Display in admin panels after init operations.
        ``tables_created`` can be shown as a collapsible list.
    """

    tables_created: list[str] = Field(
        default_factory=list,
        description="Names of tables created during initialization",
    )
    dry_run: bool = Field(
        default=False,
        description="If True, no changes were made (preview mode)",
    )


class TableCountSchema(BaseModel):
    """Row count for a single database table.

    UI Hints:
        Display in a summary table with columns: Table Name, Row Count.
        Useful for capacity planning dashboards.
    """

    table: str = Field(description="Table name (e.g., 'core_executions')")
    count: int = Field(default=0, description="Number of rows in the table")


class PurgeResultSchema(BaseModel):
    """Result of a data purge operation.

    UI Hints:
        Show in admin panel with confirmation dialog.
        Display ``rows_deleted`` prominently; list tables in expandable section.
    """

    rows_deleted: int = Field(default=0, description="Total rows deleted across all tables")
    tables_purged: list[str] = Field(
        default_factory=list,
        description="Tables that had data removed",
    )
    dry_run: bool = Field(
        default=False,
        description="If True, no deletions occurred (preview mode)",
    )


class DatabaseHealthSchema(BaseModel):
    """Database connectivity and health status.

    UI Hints:
        Display as a status card with green/red indicator based on ``connected``.
        Show ``latency_ms`` as a tooltip or secondary metric.
    """

    connected: bool = Field(default=False, description="True if database is reachable")
    backend: str = Field(
        default="",
        description="Database backend type: 'sqlite', 'postgresql', 'mysql', 'oracle'",
    )
    table_count: int = Field(default=0, description="Number of managed tables present")
    latency_ms: float = Field(default=0.0, description="Connection latency in milliseconds")


# ── Workflow ─────────────────────────────────────────────────────────────


class WorkflowSummarySchema(BaseModel):
    """Compact workflow representation for list views.

    UI Hints:
        Table columns: Name, Step Count, Description (truncated).
        Click row to navigate to workflow detail view.
    """

    name: str = Field(description="Unique workflow identifier (e.g., 'daily_etl')")
    step_count: int = Field(default=0, description="Number of steps in the workflow")
    description: str = Field(default="", description="Human-readable workflow description")


class ExecutionPolicySchema(BaseModel):
    """Execution policy for a workflow (sequential/parallel, failure handling).

    UI Hints:
        Display as a summary line: "Sequential · Stop on failure · No timeout".
        Mode badge: sequential=blue, parallel=purple.
    """

    mode: str = Field(default="sequential", description="Execution mode: 'sequential' or 'parallel'")
    max_concurrency: int = Field(default=4, description="Max concurrent steps (parallel mode only)")
    on_failure: str = Field(default="stop", description="Failure policy: 'stop' or 'continue'")
    timeout_minutes: int | None = Field(default=None, description="Timeout for entire workflow run (minutes)")


class WorkflowStepSchema(BaseModel):
    """Single step within a workflow definition.

    UI Hints:
        Render in a step-graph visualization or ordered list.
        Show depends_on to draw DAG edges between steps.
        Show metadata in a tooltip or expandable section.
    """

    name: str = Field(default="", description="Step identifier within the workflow")
    description: str = Field(default="", description="What this step does")
    operation: str = Field(default="", description="Registered operation name this step executes")
    depends_on: list[str] = Field(default_factory=list, description="Step names this step depends on (DAG edges)")
    params: dict[str, Any] = Field(default_factory=dict, description="Step-specific parameter overrides")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Step configuration (retries, timeout, dependencies)",
    )


class WorkflowDetailSchema(BaseModel):
    """Full workflow definition with step graph.

    UI Hints:
        Display in detail drawer with step visualization.
        Show steps as a DAG or sequential list depending on dependencies.
        Policy summary: "{mode} · on_failure={on_failure} · timeout={timeout_minutes}min".
    """

    name: str = Field(description="Unique workflow identifier")
    steps: list[WorkflowStepSchema] = Field(
        default_factory=list,
        description="Ordered list of workflow steps",
    )
    description: str = Field(default="", description="Workflow purpose and behavior")
    domain: str = Field(default="", description="Domain this workflow belongs to (e.g., 'core', 'quality')")
    version: int = Field(default=1, description="Workflow schema version")
    policy: ExecutionPolicySchema = Field(
        default_factory=ExecutionPolicySchema,
        description="Execution policy: mode, concurrency, failure handling, timeout",
    )
    tags: list[str] = Field(default_factory=list, description="Tags for filtering and categorization")
    defaults: dict[str, Any] = Field(
        default_factory=dict,
        description="Default parameters applied to all steps",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Workflow-level configuration and tags",
    )


# ── Runs ─────────────────────────────────────────────────────────────────


class RunSummarySchema(BaseModel):
    """Compact run representation for list views.

    UI Hints:
        Table columns: Run ID (monospace), Workflow, Status (badge),
        Started At, Duration.
        Status badge colors: pending=gray, running=blue, completed=green,
        failed=red, cancelled=orange, dead_lettered=purple.
        Duration should be computed from ``started_at`` and ``finished_at`` if
        ``duration_ms`` is None.
    """

    run_id: str = Field(description="Unique run identifier (UUID format)")
    workflow: str | None = Field(
        default="",
        description="Workflow name for this run",
    )
    status: str = Field(
        default="",
        description="Execution status: pending|running|completed|failed|cancelled|dead_lettered",
    )
    started_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp when execution began",
    )
    finished_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp when execution completed (null if running)",
    )
    duration_ms: float | None = Field(
        default=None,
        description="Execution duration in milliseconds (computed field)",
    )


class RunDetailSchema(RunSummarySchema):
    """Full run representation with parameters, result, and events.

    UI Hints:
        Display in detail drawer with tabs: Overview, Parameters, Result, Events.
        Error field should render in an error panel with monospace font.
        Events list should be collapsible and show most recent first.
    """

    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters passed to the run",
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="Output data from successful execution",
    )
    error: str | None = Field(
        default=None,
        description="Error message if status is 'failed' (show in error panel)",
    )
    events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Event-sourced execution history",
    )


class RunAcceptedSchema(BaseModel):
    """Acknowledgement returned when a run is submitted (202 Accepted).

    UI Hints:
        Show as a toast notification: "Run {run_id} submitted".
        If dry_run=True, indicate "Dry run - no execution".
    """

    run_id: str | None = Field(
        default=None,
        description="Assigned run identifier (None for dry-run)",
    )
    dry_run: bool = Field(
        default=False,
        description="True if this was a preview (no execution queued)",
    )
    would_execute: bool = Field(
        default=True,
        description="True if the run would execute (idempotency check passed)",
    )


class RunEventSchema(BaseModel):
    """Single event from a run's event-sourced history.

    UI Hints:
        Display in a timeline or log view within run detail.
        event_type as a badge, timestamp as relative time ("2m ago"),
        message as the primary text.
    """

    event_id: str = Field(default="", description="Unique event identifier")
    run_id: str = Field(default="", description="Parent run ID")
    event_type: str = Field(
        default="",
        description="Event type: 'started'|'step_completed'|'failed'|'completed'|'cancelled'",
    )
    timestamp: str = Field(default="", description="ISO-8601 timestamp of the event")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific payload (step results, error details)",
    )
    message: str = Field(default="", description="Human-readable event description")


class RunStepSchema(BaseModel):
    """Step-level timing data for workflow runs.

    UI Hints:
        Display in a step timeline or waterfall chart within run detail.
        Duration should be shown as a bar proportional to total run time.
        Status badge colors: pending=gray, running=blue, completed=green,
        failed=red, skipped=orange.
        Show row_count as a secondary metric where available.
    """

    step_id: str = Field(default="", description="Unique step identifier")
    run_id: str = Field(default="", description="Parent run ID")
    step_name: str = Field(default="", description="Step identifier within the workflow")
    step_type: str = Field(
        default="",
        description="Step type: 'operation'|'task'|'condition'|'parallel'",
    )
    step_order: int = Field(default=0, description="Execution order (0-based)")
    status: str = Field(
        default="",
        description="Step status: 'PENDING'|'RUNNING'|'COMPLETED'|'FAILED'|'SKIPPED'",
    )
    started_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp when step began execution",
    )
    completed_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp when step completed",
    )
    duration_ms: int | None = Field(
        default=None,
        description="Step execution duration in milliseconds",
    )
    row_count: int | None = Field(
        default=None,
        description="Rows processed by this step (if applicable)",
    )
    attempt: int = Field(default=1, description="Current attempt number (for retries)")
    max_attempts: int = Field(default=1, description="Maximum retry attempts configured")
    error: str | None = Field(default=None, description="Error message if step failed")
    error_category: str | None = Field(
        default=None,
        description="Error classification for retry decisions",
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional step metrics (memory, CPU, custom)",
    )


class RunLogEntrySchema(BaseModel):
    """Single log line from a run execution.

    UI Hints:
        Render in monospace font with color-coded level badges.
        Level colors: DEBUG=gray, INFO=blue, WARN=yellow, ERROR=red.
        step_name enables filtering to specific step context.
        timestamp should show absolute time with millisecond precision.
    """

    timestamp: str = Field(description="ISO-8601 timestamp with milliseconds")
    level: str = Field(default="INFO", description="Log level: DEBUG|INFO|WARN|ERROR")
    message: str = Field(description="Log message text")
    step_name: str | None = Field(
        default=None,
        description="Step name context (null for run-level logs)",
    )
    logger: str = Field(default="", description="Logger name (e.g., 'spine.operations.etl')")
    line_number: int = Field(default=0, description="Sequential line number in log output")


# ── Schedule ─────────────────────────────────────────────────────────────


class ScheduleSummarySchema(BaseModel):
    """Compact schedule representation for list views.

    UI Hints:
        Table columns: Schedule ID, Name, Target, Cron/Interval, Enabled (toggle), Next Run.
        Enabled should be a toggle switch for inline updates.
        next_run_at should show relative time ("in 2 hours").
    """

    schedule_id: str = Field(description="Unique schedule identifier")
    name: str = Field(default="", description="Human-readable schedule name")
    target_type: str = Field(default="operation", description="Target type: 'operation' or 'workflow'")
    target_name: str = Field(default="", description="Target operation or workflow name")
    cron_expression: str | None = Field(
        default=None,
        description="Cron expression (e.g., '0 9 * * *' for daily at 9am)",
    )
    interval_seconds: int | None = Field(
        default=None,
        description="Interval in seconds (alternative to cron)",
    )
    enabled: bool = Field(default=True, description="Whether the schedule is active")
    next_run_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp of next scheduled execution",
    )


class ScheduleDetailSchema(ScheduleSummarySchema):
    """Full schedule configuration with history.

    UI Hints:
        Display in detail drawer with sections: Configuration, History.
        last_run_at shows most recent execution timestamp.
    """

    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters passed to each workflow invocation",
    )
    last_run_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp of most recent execution",
    )
    last_run_status: str | None = Field(
        default=None,
        description="Status of most recent execution: COMPLETED, FAILED",
    )
    created_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp when schedule was created",
    )
    version: int = Field(default=1, description="Schedule version number")


# ── Dead-letter queue ────────────────────────────────────────────────────


class DeadLetterSchema(BaseModel):
    """Entry in the dead-letter queue (failed items after retry exhaustion).

    UI Hints:
        Table columns: ID, Workflow, Error (truncated), Created At, Replay Count.
        Error should expand on hover/click to show full message.
        Include "Replay" action button per row.
    """

    id: str = Field(description="Dead-letter entry identifier")
    workflow: str = Field(default="", description="Source workflow that failed")
    error: str = Field(default="", description="Error message from final failure")
    created_at: str = Field(default="", description="ISO-8601 timestamp when moved to DLQ")
    replay_count: int = Field(default=0, description="Number of replay attempts made")


# ── Quality ──────────────────────────────────────────────────────────────


class QualityResultSchema(BaseModel):
    """Quality check result for a workflow.

    UI Hints:
        Display as a scorecard with progress bar for score (0-100%).
        Show checks_passed/checks_failed as a ratio badge.
        Color-code score: >=90 green, >=70 yellow, <70 red.
    """

    workflow: str = Field(default="", description="Workflow that was checked")
    checks_passed: int = Field(default=0, description="Number of quality checks that passed")
    checks_failed: int = Field(default=0, description="Number of quality checks that failed")
    score: float = Field(
        default=0.0,
        description="Quality score as percentage (0.0-100.0)",
    )
    run_at: str = Field(default="", description="ISO-8601 timestamp of the quality check")


# ── Anomaly ──────────────────────────────────────────────────────────────


class AnomalySchema(BaseModel):
    """Detected anomaly in workflow metrics.

    UI Hints:
        Table columns: Severity (badge), Workflow, Metric, Value, Threshold, Detected At.
        Severity badges: info=blue, warning=yellow, critical=red.
        Value should highlight if exceeds threshold (red text).
    """

    id: str = Field(default="", description="Unique anomaly identifier")
    workflow: str = Field(default="", description="Workflow where anomaly was detected")
    metric: str = Field(
        default="",
        description="Metric name (e.g., 'row_count', 'latency_p99')",
    )
    severity: str = Field(
        default="",
        description="Severity level: 'info'|'warning'|'critical'",
    )
    value: float = Field(default=0.0, description="Observed metric value")
    threshold: float = Field(default=0.0, description="Expected threshold that was breached")
    detected_at: str = Field(default="", description="ISO-8601 timestamp of detection")


# ── Health / capabilities ────────────────────────────────────────────────


class HealthStatusSchema(BaseModel):
    """System health status with dependency checks.

    UI Hints:
        Display as a status dashboard card.
        Overall status as large badge; checks as expandable list.
        database dict shows backend-specific health info.
    """

    status: str = Field(
        default="healthy",
        description="Overall health: 'healthy'|'degraded'|'unhealthy'",
    )
    database: dict[str, Any] = Field(
        default_factory=dict,
        description="Database health details (connected, backend, latency)",
    )
    checks: dict[str, Any] = Field(
        default_factory=dict,
        description="Individual dependency check results",
    )
    version: str = Field(default="", description="API version string")


class CapabilitiesSchema(BaseModel):
    """Server feature flags and tier information.

    UI Hints:
        Display as a feature matrix or capability badges.
        Useful for conditionally showing/hiding UI features.
        tier: 'minimal'|'standard'|'full' determines available features.
    """

    tier: str = Field(
        default="",
        description="Deployment tier: 'minimal'|'standard'|'full'",
    )
    sync_execution: bool = Field(
        default=True,
        description="Synchronous execution supported (always True)",
    )
    async_execution: bool = Field(
        default=False,
        description="Async/background execution via Celery workers",
    )
    scheduling: bool = Field(
        default=False,
        description="Scheduled workflow execution available",
    )
    rate_limiting: bool = Field(
        default=False,
        description="Rate limiting middleware active",
    )
    execution_history: bool = Field(
        default=True,
        description="Execution history tracking enabled",
    )
    dlq: bool = Field(
        default=True,
        description="Dead-letter queue functionality available",
    )
