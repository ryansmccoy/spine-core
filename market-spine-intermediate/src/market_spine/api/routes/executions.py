"""Execution management endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from market_spine.dispatcher import Dispatcher
from market_spine.repositories.executions import ExecutionRepository, ExecutionEventRepository

router = APIRouter()


# -------------------------------------------------------------------------
# Schemas
# -------------------------------------------------------------------------


class ExecutionCreate(BaseModel):
    """Request to create a new execution."""

    pipeline_name: str = Field(..., description="Name of the pipeline to execute")
    params: dict[str, Any] = Field(default_factory=dict, description="Pipeline parameters")
    logical_key: str | None = Field(None, description="Optional key for concurrency control")


class ExecutionResponse(BaseModel):
    """Execution details."""

    id: str
    pipeline_name: str
    params: dict[str, Any] | None
    logical_key: str | None
    status: str
    backend: str | None
    backend_run_id: str | None
    parent_execution_id: str | None
    created_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}


class ExecutionList(BaseModel):
    """List of executions."""

    items: list[ExecutionResponse]
    total: int


class ExecutionEvent(BaseModel):
    """Execution event."""

    id: str
    execution_id: str
    event_type: str
    payload: dict[str, Any] | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class SubmitResponse(BaseModel):
    """Response for execution submission."""

    execution_id: str
    status: str
    message: str


# -------------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------------


@router.post("", response_model=SubmitResponse, status_code=202)
async def submit_execution(request: ExecutionCreate):
    """
    Submit a pipeline for execution.

    The execution will be queued and processed by the worker.
    Returns immediately with the execution ID.
    """
    dispatcher = Dispatcher()

    try:
        execution_id = dispatcher.submit(
            pipeline_name=request.pipeline_name,
            params=request.params,
            logical_key=request.logical_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return SubmitResponse(
        execution_id=execution_id,
        status="queued",
        message=f"Execution {execution_id} submitted successfully",
    )


@router.get("", response_model=ExecutionList)
async def list_executions(
    status: str | None = Query(None, description="Filter by status"),
    pipeline_name: str | None = Query(None, description="Filter by pipeline name"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List executions with optional filters."""
    items = ExecutionRepository.list_executions(
        status=status,
        pipeline_name=pipeline_name,
        limit=limit,
        offset=offset,
    )

    return ExecutionList(
        items=[ExecutionResponse(**item) for item in items],
        total=len(items),  # Note: This is page count, not total count
    )


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: str):
    """Get execution details by ID."""
    execution = ExecutionRepository.get(execution_id)

    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    return ExecutionResponse(**execution)


@router.get("/{execution_id}/events", response_model=list[ExecutionEvent])
async def get_execution_events(execution_id: str):
    """Get events for an execution."""
    # Verify execution exists
    execution = ExecutionRepository.get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    events = ExecutionEventRepository.get_events(execution_id)
    return [ExecutionEvent(**event) for event in events]


@router.post("/{execution_id}/cancel", response_model=SubmitResponse)
async def cancel_execution(execution_id: str):
    """
    Request cancellation of an execution.

    Best-effort cancellation:
    - Pending/queued executions are cancelled immediately
    - Running executions may not be cancellable
    """
    execution = ExecutionRepository.get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    if execution["status"] in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel execution in status: {execution['status']}",
        )

    dispatcher = Dispatcher()
    success = dispatcher.cancel(execution_id)

    if success:
        return SubmitResponse(
            execution_id=execution_id,
            status="cancelled",
            message="Execution cancelled successfully",
        )
    else:
        return SubmitResponse(
            execution_id=execution_id,
            status="cancel_requested",
            message="Cancellation requested (running executions may not be cancellable)",
        )
