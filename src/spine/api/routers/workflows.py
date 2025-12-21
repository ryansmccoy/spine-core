"""
Workflow router — list, inspect, and trigger workflows.

GET  /workflows
GET  /workflows/{name}
POST /workflows/{name}/run

Manifesto:
    Workflows are the primary unit of work.  These endpoints let
    dashboards list, inspect, and trigger any registered workflow.

Tags:
    spine-core, api, workflows, trigger, inspect, list

Doc-Types:
    api-reference
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field

from spine.api.deps import OpContext
from spine.api.schemas.common import PagedResponse, PageMeta, SuccessResponse
from spine.api.schemas.domains import (
    ExecutionPolicySchema,
    RunAcceptedSchema,
    WorkflowDetailSchema,
    WorkflowStepSchema,
    WorkflowSummarySchema,
)
from spine.api.utils import _dc, _handle_error

router = APIRouter(prefix="/workflows")


class RunWorkflowBody(BaseModel):
    """Request body for triggering a workflow."""
    params: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = ""
    dry_run: bool = False


@router.get("", response_model=PagedResponse[WorkflowSummarySchema])
def list_workflows(ctx: OpContext):
    """List all registered workflows.

    Returns all workflow definitions available in the system.
    Use this to populate workflow selection dropdowns or catalog views.

    Args:
        ctx: Operation context with database connection.

    Returns:
        PagedResponse containing list of WorkflowSummarySchema items.

    Example:
        GET /api/v1/workflows

        Response:
        {
            "data": [
                {"name": "daily_etl", "step_count": 5, "description": "Daily ETL operation"},
                {"name": "report_gen", "step_count": 3, "description": "Generate reports"}
            ],
            "page": {"total": 2, "limit": 50, "offset": 0, "has_more": false}
        }
    """
    from spine.ops.workflows import list_workflows as _list

    result = _list(ctx)
    if not result.success:
        return _handle_error(result)
    items = [WorkflowSummarySchema(**_dc(s)) for s in (result.data or [])]
    return PagedResponse(
        data=items,
        page=PageMeta(
            total=result.total or len(items),
            limit=result.limit or 50,
            offset=result.offset or 0,
            has_more=result.has_more or False,
        ),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.get("/{name}", response_model=SuccessResponse[WorkflowDetailSchema])
def get_workflow(ctx: OpContext, name: str = Path(..., description="Workflow name")):
    """Get workflow definition and step graph.

    Returns the full workflow definition including all steps and their
    configuration. Use for workflow detail views and step visualization.

    Args:
        ctx: Operation context with database connection.
        name: The unique workflow identifier.

    Returns:
        SuccessResponse containing WorkflowDetailSchema with steps.

    Raises:
        404 NOT_FOUND: Workflow with specified name does not exist.

    Example:
        GET /api/v1/workflows/daily_etl

        Response:
        {
            "data": {
                "name": "daily_etl",
                "description": "Daily ETL operation",
                "steps": [
                    {"name": "extract", "description": "Extract from sources"},
                    {"name": "transform", "description": "Apply transformations"},
                    {"name": "load", "description": "Load to warehouse"}
                ]
            }
        }
    """
    from spine.ops.requests import GetWorkflowRequest
    from spine.ops.workflows import get_workflow as _get

    result = _get(ctx, GetWorkflowRequest(name=name))
    if not result.success:
        return _handle_error(result)

    raw = _dc(result.data)
    meta = raw.get("metadata", {})

    # Map steps with expanded fields
    steps = []
    for s in raw.get("steps", []):
        steps.append(WorkflowStepSchema(
            name=s.get("name", ""),
            description=s.get("description", ""),
            operation=s.get("operation", ""),
            depends_on=s.get("depends_on", []),
            params=s.get("params", {}),
            metadata={k: v for k, v in s.items() if k not in ("name", "description", "operation", "depends_on", "params")},
        ))

    # Map policy from metadata
    policy_raw = meta.get("policy", {})
    policy = ExecutionPolicySchema(
        mode=policy_raw.get("mode", "sequential"),
        max_concurrency=policy_raw.get("max_concurrency", 4),
        on_failure=policy_raw.get("on_failure", "stop"),
        timeout_minutes=policy_raw.get("timeout_minutes"),
    )

    detail = WorkflowDetailSchema(
        name=raw.get("name", ""),
        steps=steps,
        description=raw.get("description", ""),
        domain=meta.get("domain", ""),
        version=meta.get("version", 1),
        policy=policy,
        tags=meta.get("tags", []),
        defaults=meta.get("defaults", {}),
        metadata=meta,
    )

    return SuccessResponse(
        data=detail,
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.post("/{name}/run", response_model=SuccessResponse[RunAcceptedSchema], status_code=202)
def run_workflow(
    ctx: OpContext,
    name: str = Path(..., description="Workflow name to execute"),
    body: RunWorkflowBody | None = None,
):
    """Trigger a workflow execution.

    Queues the workflow for execution and returns immediately.
    The workflow runs asynchronously via configured workers.

    Args:
        ctx: Operation context with database connection.
        name: The workflow name to execute.
        body: Optional execution parameters and idempotency key.

    Returns:
        SuccessResponse containing RunAcceptedSchema with the assigned run_id.
        Status code 202 indicates accepted for processing.

    Raises:
        404 NOT_FOUND: Workflow with specified name does not exist.
        409 CONFLICT: Idempotency key collision (run already exists).

    Example:
        POST /api/v1/workflows/daily_etl/run
        {"params": {"date": "2026-02-13"}}

        Response (202):
        {"data": {"run_id": "abc-123", "dry_run": false, "would_execute": true}}
    """
    from spine.ops.requests import RunWorkflowRequest
    from spine.ops.workflows import run_workflow as _run

    body = body or RunWorkflowBody()
    ctx.dry_run = body.dry_run
    request = RunWorkflowRequest(
        name=name,
        params=body.params,
        idempotency_key=body.idempotency_key,
    )
    result = _run(ctx, request)
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=RunAcceptedSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )
