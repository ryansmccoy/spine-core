"""Workflow history table models (02_workflow_history.sql).

Models for workflow execution history: runs, steps, and lifecycle events.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# core_workflow_runs
# ---------------------------------------------------------------------------


@dataclass
class WorkflowRun:
    """Workflow execution tracking row (``core_workflow_runs``)."""

    run_id: str = ""
    workflow_name: str = ""
    workflow_version: int = 1
    domain: str | None = None
    partition_key: str | None = None  # JSON logical key
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    params: str | None = None  # JSON input parameters
    outputs: str | None = None  # JSON final outputs
    error: str | None = None
    error_category: str | None = None
    error_retryable: int | None = None
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    triggered_by: str = "manual"  # manual, schedule, api, parent_workflow
    parent_run_id: str | None = None
    schedule_id: str | None = None
    created_at: str = ""
    created_by: str | None = None
    capture_id: str | None = None


# ---------------------------------------------------------------------------
# core_workflow_steps
# ---------------------------------------------------------------------------


@dataclass
class WorkflowStep:
    """Step within a workflow run (``core_workflow_steps``)."""

    step_id: str = ""
    run_id: str = ""
    step_name: str = ""
    step_type: str = ""  # pipeline, task, condition, parallel
    step_order: int = 0
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    params: str | None = None  # JSON input parameters
    outputs: str | None = None  # JSON step outputs
    error: str | None = None
    error_category: str | None = None
    row_count: int | None = None
    metrics: str | None = None  # JSON additional metrics
    attempt: int = 1
    max_attempts: int = 1
    execution_id: str | None = None
    created_at: str = ""


# ---------------------------------------------------------------------------
# core_workflow_events
# ---------------------------------------------------------------------------


@dataclass
class WorkflowEvent:
    """Immutable lifecycle event for a workflow run (``core_workflow_events``)."""

    id: int | None = None
    run_id: str = ""
    step_id: str | None = None
    event_type: str = ""  # started, completed, failed, retrying, skipped, cancelled
    timestamp: str = ""
    payload: str | None = None  # JSON event-specific data
    idempotency_key: str | None = None
