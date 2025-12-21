"""Work specification - what to run.

This module defines WorkSpec, the canonical contract for specifying work
in spine-core. All execution types (tasks, operations, workflows, steps)
use this single specification format.

Manifesto:
    A single WorkSpec schema means any executor can accept any
    work request without format translation.  This eliminates
    per-executor request models and keeps submission uniform.

Tags:
    spine-core, execution, spec, work-spec, request-model

Doc-Types:
    api-reference
"""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class WorkSpec:
    """Universal work specification for tasks, operations, workflows, and steps.

    This is the canonical contract that makes spine-core runtime-agnostic.
    Whether you execute with Celery, Airflow, K8s Jobs, or local threads,
    you always submit a WorkSpec.

    Example:
        >>> spec = WorkSpec(kind="task", name="send_email", params={"to": "user@example.com"})
        >>> spec = task_spec("send_email", {"to": "user@example.com"})  # convenience
    """

    # === WHAT TO RUN ===
    kind: Literal["task", "operation", "workflow", "step"]
    """Type of work: task (single unit), operation (registered operation),
    workflow (multi-step), or step (workflow sub-task)"""

    name: str
    """Handler name, operation name, workflow name, or step name"""

    params: dict[str, Any] = field(default_factory=dict)
    """Execution parameters passed to the handler"""

    # === TRACKING ===
    idempotency_key: str | None = None
    """Prevent duplicate executions. If provided and a run with this key exists,
    return existing run instead of creating new one."""

    correlation_id: str | None = None
    """Link related runs (e.g., all steps in a workflow share a correlation_id)"""

    # === ROUTING ===
    priority: Literal["realtime", "high", "normal", "low", "slow"] = "normal"
    """Priority level for executor routing"""

    lane: str = "default"
    """Queue/lane name for executor routing (e.g., 'gpu', 'cpu', 'io-bound')"""

    # === CONTEXT ===
    parent_run_id: str | None = None
    """For workflow steps, the run_id of the parent workflow"""

    trigger_source: str = "api"
    """How this work was triggered: api, schedule, webhook, manual, etc."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional context (tenant_id, user_id, trace_id, etc.)"""

    # === RETRY POLICY ===
    max_retries: int = 3
    """Maximum retry attempts on failure"""

    retry_delay_seconds: int = 60
    """Delay between retries"""


def task_spec(name: str, params: dict | None = None, **kwargs) -> WorkSpec:
    """Convenience constructor for task specs.

    Example:
        >>> spec = task_spec("send_email", {"to": "user@example.com"}, priority="high")
    """
    return WorkSpec(kind="task", name=name, params=params or {}, **kwargs)


def operation_spec(name: str, params: dict | None = None, **kwargs) -> WorkSpec:
    """Convenience constructor for operation specs.

    Example:
        >>> spec = operation_spec("ingest_otc", {"date": "2026-01-15"})
    """
    return WorkSpec(kind="operation", name=name, params=params or {}, **kwargs)


def workflow_spec(name: str, params: dict | None = None, **kwargs) -> WorkSpec:
    """Convenience constructor for workflow specs.

    Example:
        >>> spec = workflow_spec("daily_ingest", {"tier": "NMS_TIER_1"})
    """
    return WorkSpec(kind="workflow", name=name, params=params or {}, **kwargs)


def step_spec(name: str, params: dict | None = None, parent_run_id: str | None = None, **kwargs) -> WorkSpec:
    """Convenience constructor for workflow step specs.

    Automatically sets correlation_id to parent_run_id if not provided.

    Example:
        >>> spec = step_spec("validate", {"data": results}, parent_run_id="abc-123")
    """
    # Auto-set correlation_id to parent_run_id if not explicitly provided
    if parent_run_id and "correlation_id" not in kwargs:
        kwargs["correlation_id"] = parent_run_id

    return WorkSpec(kind="step", name=name, params=params or {}, parent_run_id=parent_run_id, **kwargs)
