"""Execution API endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from market_spine.core.models import ExecutionStatus, TriggerSource
from market_spine.execution.ledger import ExecutionLedger
from market_spine.execution.dispatcher import Dispatcher
from market_spine.backends.celery_backend import CeleryBackend
from market_spine.pipelines.registry import get_registry
from market_spine.observability.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class SubmitExecutionRequest(BaseModel):
    """Request to submit a pipeline execution."""

    pipeline: str = Field(..., description="Pipeline name to execute")
    params: dict[str, Any] = Field(default_factory=dict, description="Pipeline parameters")
    lane: str = Field(default="default", description="Execution lane")


class ExecutionResponse(BaseModel):
    """Execution details response."""

    id: str
    pipeline: str
    params: dict[str, Any]
    status: str
    lane: str
    trigger_source: str
    parent_execution_id: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    result: dict[str, Any] | None
    error: str | None
    retry_count: int


class ExecutionEventResponse(BaseModel):
    """Execution event response."""

    id: str
    execution_id: str
    event_type: str
    timestamp: str
    data: dict[str, Any]


class PipelineInfo(BaseModel):
    """Pipeline information."""

    name: str
    description: str
    requires_lock: bool


@router.get("/pipelines", response_model=list[PipelineInfo])
async def list_pipelines():
    """List all available pipelines."""
    registry = get_registry()
    return [
        PipelineInfo(
            name=p.name,
            description=p.description,
            requires_lock=p.requires_lock,
        )
        for p in registry.all_definitions()
    ]


@router.post("", response_model=ExecutionResponse, status_code=201)
async def submit_execution(request: SubmitExecutionRequest):
    """
    Submit a pipeline execution.

    This is an enqueue-only endpoint - it creates an execution record
    and submits it to the backend. The actual pipeline runs asynchronously.
    """
    # Validate pipeline exists
    registry = get_registry()
    if registry.get(request.pipeline) is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown pipeline: {request.pipeline}",
        )

    try:
        ledger = ExecutionLedger()
        backend = CeleryBackend()
        dispatcher = Dispatcher(ledger, backend)

        execution = dispatcher.submit(
            pipeline=request.pipeline,
            params=request.params,
            lane=request.lane,
            trigger_source=TriggerSource.API,
        )

        logger.info(
            "execution_submitted_via_api",
            execution_id=execution.id,
            pipeline=request.pipeline,
        )

        return _execution_to_response(execution)

    except Exception as e:
        logger.error("execution_submission_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=list[ExecutionResponse])
async def list_executions(
    pipeline: str | None = Query(None, description="Filter by pipeline"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(100, le=1000, description="Max results"),
):
    """List executions with optional filters."""
    try:
        ledger = ExecutionLedger()
        status_enum = ExecutionStatus(status) if status else None
        executions = ledger.list_executions(
            pipeline=pipeline,
            status=status_enum,
            limit=limit,
        )
        return [_execution_to_response(e) for e in executions]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("list_executions_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: str):
    """Get execution details by ID."""
    ledger = ExecutionLedger()
    execution = ledger.get_execution(execution_id)

    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    return _execution_to_response(execution)


@router.get("/{execution_id}/events", response_model=list[ExecutionEventResponse])
async def get_execution_events(execution_id: str):
    """Get events for an execution."""
    ledger = ExecutionLedger()

    # Check execution exists
    execution = ledger.get_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    events = ledger.get_events(execution_id)
    return [
        ExecutionEventResponse(
            id=e.id,
            execution_id=e.execution_id,
            event_type=e.event_type.value,
            timestamp=e.timestamp.isoformat(),
            data=e.data,
        )
        for e in events
    ]


@router.post("/{execution_id}/cancel", response_model=dict)
async def cancel_execution(execution_id: str):
    """Cancel a pending or running execution."""
    ledger = ExecutionLedger()
    backend = CeleryBackend()
    dispatcher = Dispatcher(ledger, backend)

    if dispatcher.cancel(execution_id):
        return {"status": "cancelled", "execution_id": execution_id}
    else:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel execution (not found or already completed)",
        )


def _execution_to_response(execution) -> ExecutionResponse:
    """Convert Execution model to response."""
    return ExecutionResponse(
        id=execution.id,
        pipeline=execution.pipeline,
        params=execution.params,
        status=execution.status.value,
        lane=execution.lane,
        trigger_source=execution.trigger_source.value,
        parent_execution_id=execution.parent_execution_id,
        created_at=execution.created_at.isoformat(),
        started_at=execution.started_at.isoformat() if execution.started_at else None,
        completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
        result=execution.result,
        error=execution.error,
        retry_count=execution.retry_count,
    )
