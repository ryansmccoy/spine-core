"""Workflow management endpoints.

Provides API access to workflow runs and execution history.

Follows API Design Guardrails:
- Resource-style URLs: /v1/workflows/{name}/runs
- Pagination: offset/limit with has_more
- Standard error envelope
"""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

router = APIRouter()


# =============================================================================
# SCHEMAS (Following FRONTEND_CONTRACT_PRINCIPLES.md)
# =============================================================================


class PaginationMeta(BaseModel):
    """Standard pagination metadata."""
    offset: int
    limit: int
    total: int
    has_more: bool


class WorkflowRunCreate(BaseModel):
    """Request to trigger a workflow run."""
    params: dict[str, Any] = Field(default_factory=dict, description="Workflow parameters")
    partition_key: dict[str, Any] | None = Field(None, description="Partition context")


class WorkflowRunSummary(BaseModel):
    """Summary of a workflow run for list views."""
    run_id: str
    workflow_name: str
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
    domain: str | None
    partition_key: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    total_steps: int
    completed_steps: int
    failed_steps: int
    triggered_by: str
    error: str | None

    model_config = {"from_attributes": True}


class WorkflowStepDetail(BaseModel):
    """Step execution details."""
    step_id: str
    step_name: str
    step_type: str
    step_order: int
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED"]
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    row_count: int | None
    error: str | None
    error_category: str | None
    attempt: int

    model_config = {"from_attributes": True}


class WorkflowRunDetail(BaseModel):
    """Full workflow run details with steps."""
    run_id: str
    workflow_name: str
    workflow_version: int
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
    domain: str | None
    partition_key: dict[str, Any] | None
    
    # Timing
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    
    # Context
    params: dict[str, Any] | None
    outputs: dict[str, Any] | None
    
    # Error
    error: str | None
    error_category: str | None
    error_retryable: bool | None
    
    # Metrics
    total_steps: int
    completed_steps: int
    failed_steps: int
    skipped_steps: int
    
    # Trigger
    triggered_by: str
    parent_run_id: str | None
    schedule_id: str | None
    
    # Steps (embedded for detail view)
    steps: list[WorkflowStepDetail] = Field(default_factory=list)
    
    # Audit
    created_at: datetime
    created_by: str | None
    capture_id: str | None

    model_config = {"from_attributes": True}


class WorkflowRunList(BaseModel):
    """Paginated list of workflow runs."""
    data: list[WorkflowRunSummary]
    pagination: PaginationMeta


class WorkflowTriggerResponse(BaseModel):
    """Response for workflow trigger."""
    run_id: str
    status: str
    message: str


class WorkflowCancelResponse(BaseModel):
    """Response for workflow cancellation."""
    run_id: str
    status: str
    message: str


class ErrorResponse(BaseModel):
    """Standard error response."""
    code: str
    message: str
    details: dict[str, Any] | None = None


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get(
    "",
    response_model=WorkflowRunList,
    summary="List workflow runs",
    description="Get paginated list of workflow runs with optional filtering",
)
async def list_workflow_runs(
    workflow_name: str | None = Query(None, description="Filter by workflow name"),
    domain: str | None = Query(None, description="Filter by domain"),
    status: str | None = Query(None, description="Filter by status"),
    triggered_by: str | None = Query(None, description="Filter by trigger source"),
    start_date: str | None = Query(None, description="Filter runs started after (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="Filter runs started before (YYYY-MM-DD)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=1000, description="Page size"),
):
    """
    List workflow runs with filtering and pagination.
    
    Returns summary information suitable for list views.
    Use GET /workflows/runs/{run_id} for full details.
    """
    # TODO: Implement with WorkflowHistoryRepository
    # For now, return empty list
    return WorkflowRunList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )


@router.get(
    "/{run_id}",
    response_model=WorkflowRunDetail,
    summary="Get workflow run details",
    description="Get full details of a workflow run including all steps",
)
async def get_workflow_run(
    run_id: str = Path(..., description="Workflow run ID"),
    include_steps: bool = Query(True, description="Include step details"),
):
    """
    Get detailed information about a specific workflow run.
    
    Includes all steps and their execution details.
    """
    # TODO: Implement with WorkflowHistoryRepository
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Workflow run not found: {run_id}"},
    )


@router.post(
    "/{workflow_name}/trigger",
    response_model=WorkflowTriggerResponse,
    status_code=202,
    summary="Trigger workflow",
    description="Start a new workflow run",
)
async def trigger_workflow(
    workflow_name: str = Path(..., description="Workflow name"),
    request: WorkflowRunCreate = ...,
):
    """
    Trigger a new workflow run.
    
    Returns immediately with the run ID. The workflow executes asynchronously.
    Use GET /workflows/runs/{run_id} to check status.
    """
    # TODO: Implement with WorkflowRunner
    # 1. Validate workflow exists
    # 2. Create run record
    # 3. Queue for execution
    # 4. Return run_id
    
    return WorkflowTriggerResponse(
        run_id="pending-implementation",
        status="PENDING",
        message=f"Workflow {workflow_name} queued for execution",
    )


@router.post(
    "/{run_id}/cancel",
    response_model=WorkflowCancelResponse,
    summary="Cancel workflow run",
    description="Request cancellation of a running workflow",
)
async def cancel_workflow_run(
    run_id: str = Path(..., description="Workflow run ID"),
):
    """
    Request cancellation of a running workflow.
    
    The workflow will be marked for cancellation. Steps in progress
    may complete before the workflow stops.
    """
    # TODO: Implement cancellation
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Workflow run not found: {run_id}"},
    )


@router.post(
    "/{run_id}/retry",
    response_model=WorkflowTriggerResponse,
    status_code=202,
    summary="Retry failed workflow",
    description="Retry a failed workflow run from the point of failure",
)
async def retry_workflow_run(
    run_id: str = Path(..., description="Workflow run ID to retry"),
    from_step: str | None = Query(None, description="Step to restart from (default: first failed)"),
):
    """
    Retry a failed workflow run.
    
    By default, restarts from the first failed step. Use from_step
    to specify a different starting point.
    """
    # TODO: Implement retry logic
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Workflow run not found: {run_id}"},
    )


@router.get(
    "/{run_id}/steps",
    response_model=list[WorkflowStepDetail],
    summary="Get workflow steps",
    description="Get steps for a workflow run",
)
async def get_workflow_steps(
    run_id: str = Path(..., description="Workflow run ID"),
    status: str | None = Query(None, description="Filter by step status"),
):
    """
    Get all steps for a workflow run.
    
    Use status filter to get only failed or pending steps.
    """
    # TODO: Implement with WorkflowHistoryRepository
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Workflow run not found: {run_id}"},
    )


# =============================================================================
# WORKFLOW DEFINITIONS (Read-Only)
# =============================================================================


class WorkflowDefinition(BaseModel):
    """Workflow definition summary."""
    name: str
    domain: str | None
    description: str | None
    step_count: int
    is_active: bool


class WorkflowDefinitionList(BaseModel):
    """List of workflow definitions."""
    data: list[WorkflowDefinition]
    pagination: PaginationMeta


@router.get(
    "/definitions",
    response_model=WorkflowDefinitionList,
    summary="List workflow definitions",
    description="Get registered workflow definitions",
)
async def list_workflow_definitions(
    domain: str | None = Query(None, description="Filter by domain"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """
    List all registered workflow definitions.
    
    These are the workflows available to trigger.
    """
    # TODO: Implement with workflow registry
    return WorkflowDefinitionList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )
