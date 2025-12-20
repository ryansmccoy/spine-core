"""
Workflow operations.

List, inspect, and trigger registered workflows. The actual execution
is delegated to :class:`~spine.orchestration.workflow_runner.WorkflowRunner`
or :class:`~spine.execution.dispatcher.EventDispatcher` — this module
only provides the typed operations-layer façade.
"""

from __future__ import annotations

from typing import Any

from spine.core.logging import get_logger

from spine.core.repositories import WorkflowRunRepository
from spine.ops.context import OperationContext
from spine.ops.requests import (
    GetWorkflowRequest,
    ListWorkflowEventsRequest,
    RunWorkflowRequest,
)
from spine.ops.responses import (
    RunAccepted,
    WorkflowDetail,
    WorkflowEventSummary,
    WorkflowSummary,
)
from spine.ops.result import OperationResult, PagedResult, start_timer

logger = get_logger(__name__)


def _wf_repo(ctx: OperationContext) -> WorkflowRunRepository:
    return WorkflowRunRepository(ctx.conn)


def list_workflows(ctx: OperationContext) -> PagedResult[WorkflowSummary]:
    """List all registered workflows (from in-memory registry)."""
    timer = start_timer()

    try:
        from spine.orchestration.workflow_registry import (
            get_workflow as _get_workflow,
        )
        from spine.orchestration.workflow_registry import (
            list_workflows as _list_workflows,
        )

        names = _list_workflows()
        summaries: list[WorkflowSummary] = []

        for name in names:
            try:
                workflow = _get_workflow(name)
                summaries.append(
                    WorkflowSummary(
                        name=workflow.name,
                        step_count=len(workflow.steps),
                        description=getattr(workflow, "description", ""),
                    )
                )
            except Exception:
                summaries.append(WorkflowSummary(name=name))

        return PagedResult.from_items(
            summaries,
            total=len(summaries),
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to list workflows: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


def get_workflow(
    ctx: OperationContext,
    request: GetWorkflowRequest,
) -> OperationResult[WorkflowDetail]:
    """Get workflow definition and step graph."""
    timer = start_timer()

    if not request.name:
        return OperationResult.fail(
            "VALIDATION_FAILED",
            "Workflow name is required",
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        from spine.orchestration.workflow_registry import (
            WorkflowNotFoundError,
        )
        from spine.orchestration.workflow_registry import (
            get_workflow as _get_workflow,
        )

        try:
            workflow = _get_workflow(request.name)
        except WorkflowNotFoundError:
            return OperationResult.fail(
                "NOT_FOUND",
                f"Workflow '{request.name}' not found",
                elapsed_ms=timer.elapsed_ms,
            )

        steps: list[dict[str, Any]] = []
        for step in workflow.steps:
            step_info: dict[str, Any] = {"name": step.name}
            if hasattr(step, "pipeline_name") and step.pipeline_name:
                step_info["pipeline"] = step.pipeline_name
            if hasattr(step, "depends_on") and step.depends_on:
                step_info["depends_on"] = list(step.depends_on)
            if hasattr(step, "params") and step.params:
                step_info["params"] = step.params
            steps.append(step_info)

        # Serialize execution policy
        policy_dict: dict[str, Any] = {}
        if hasattr(workflow, "execution_policy") and workflow.execution_policy:
            policy = workflow.execution_policy
            policy_dict = {
                "mode": policy.mode.value if hasattr(policy.mode, "value") else str(policy.mode),
                "max_concurrency": getattr(policy, "max_concurrency", 4),
                "on_failure": policy.on_failure.value if hasattr(policy.on_failure, "value") else str(policy.on_failure),
                "timeout_seconds": getattr(policy, "timeout_seconds", None),
            }

        detail = WorkflowDetail(
            name=workflow.name,
            steps=steps,
            description=getattr(workflow, "description", ""),
            metadata={
                "domain": getattr(workflow, "domain", ""),
                "version": getattr(workflow, "version", 1),
                "policy": policy_dict,
                "tags": list(getattr(workflow, "tags", [])),
                "defaults": dict(getattr(workflow, "defaults", {})),
                "step_count": len(workflow.steps),
            },
        )
        return OperationResult.ok(detail, elapsed_ms=timer.elapsed_ms)

    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to get workflow: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def run_workflow(
    ctx: OperationContext,
    request: RunWorkflowRequest,
) -> OperationResult[RunAccepted]:
    """Submit a workflow for execution.

    In dry_run mode, validates the workflow exists and returns a preview.
    When executed, records the intent; actual dispatch happens at the
    transport layer via ``EventDispatcher.submit_workflow``.
    """
    timer = start_timer()

    if not request.name:
        return OperationResult.fail(
            "VALIDATION_FAILED",
            "Workflow name is required",
            elapsed_ms=timer.elapsed_ms,
        )

    # Validate workflow exists
    try:
        from spine.orchestration.workflow_registry import workflow_exists
        if not workflow_exists(request.name):
            return OperationResult.fail(
                "NOT_FOUND",
                f"Workflow '{request.name}' not found",
                elapsed_ms=timer.elapsed_ms,
            )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Registry lookup failed: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )

    if ctx.dry_run:
        return OperationResult.ok(
            RunAccepted(run_id=None, dry_run=True, would_execute=True),
            elapsed_ms=timer.elapsed_ms,
        )

    # Record the submission. The actual async dispatch is the responsibility
    # of the transport/API layer which has access to EventDispatcher.
    import uuid

    run_id = str(uuid.uuid4())
    return OperationResult.ok(
        RunAccepted(run_id=run_id, would_execute=True),
        elapsed_ms=timer.elapsed_ms,
        metadata={"workflow": request.name, "params": request.params},
    )


# ------------------------------------------------------------------ #
# Workflow Events (wires core_workflow_events)
# ------------------------------------------------------------------ #


def list_workflow_events(
    ctx: OperationContext,
    request: ListWorkflowEventsRequest,
) -> PagedResult[WorkflowEventSummary]:
    """List lifecycle events for a workflow run.

    Provides an audit trail of state transitions for debugging
    and observability.
    """
    from spine.ops.responses import WorkflowEventSummary

    timer = start_timer()

    if not request.run_id:
        return PagedResult(
            success=False,
            error=_err("VALIDATION_FAILED", "run_id is required"),
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        repo = _wf_repo(ctx)
        rows, total = repo.list_events(
            run_id=request.run_id,
            step_id=request.step_id,
            event_type=request.event_type,
            limit=request.limit,
            offset=request.offset,
        )

        import json

        summaries = []
        for r in rows:
            payload_raw = r.get("payload", "{}")
            try:
                payload = json.loads(payload_raw) if payload_raw else {}
            except (json.JSONDecodeError, TypeError):
                payload = {}

            summaries.append(
                WorkflowEventSummary(
                    id=r.get("id", 0),
                    run_id=r.get("run_id", ""),
                    step_id=r.get("step_id"),
                    event_type=r.get("event_type", ""),
                    timestamp=r.get("timestamp"),
                    payload=payload,
                )
            )

        return PagedResult.from_items(
            summaries,
            total=total,
            limit=request.limit,
            offset=request.offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to list workflow events: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _err(code: str, message: str):
    from spine.ops.result import OperationError
    return OperationError(code=code, message=message)


def _col(row: Any, idx: int, name: str, default: Any = "") -> Any:
    """Extract a column from a row that may be a dict, Row, or tuple."""
    if isinstance(row, dict):
        return row.get(name, default)
    if hasattr(row, "keys"):
        return dict(row).get(name, default)
    try:
        return row[idx]
    except (IndexError, TypeError):
        return default
