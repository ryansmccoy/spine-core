"""FastAPI application for Market Spine Advanced."""

from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from market_spine.config import get_settings
from market_spine.db import get_pool, close_pool
from market_spine.dispatcher import Dispatcher
from market_spine.pipelines import PipelineRegistry
from market_spine.repositories.executions import ExecutionRepository, ExecutionEventRepository
from market_spine.orchestration import DLQManager, ScheduleManager

logger = structlog.get_logger()


# =============================================================================
# Lifespan
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init/close resources."""
    settings = get_settings()
    get_pool()  # Initialize connection pool
    logger.info("application_started", backend=settings.backend_type)
    yield
    close_pool()
    logger.info("application_stopped")


# =============================================================================
# App Setup
# =============================================================================

app = FastAPI(
    title="Market Spine Advanced",
    description="Analytics pipeline system with Celery, DLQ, and scheduling",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Models
# =============================================================================


class HealthResponse(BaseModel):
    status: str
    version: str
    backend: str


class SubmitRequest(BaseModel):
    pipeline_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    max_retries: int | None = None
    skip_dedup: bool = False


class SubmitResponse(BaseModel):
    execution_id: str
    pipeline_name: str
    status: str = "pending"


class ExecutionResponse(BaseModel):
    id: str
    pipeline_name: str
    params: dict[str, Any]
    status: str
    backend: str | None
    retry_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}


class PipelineInfo(BaseModel):
    name: str
    description: str


class ScheduleRequest(BaseModel):
    pipeline_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    cron_expression: str
    description: str | None = None


class ScheduleResponse(BaseModel):
    id: str
    pipeline_name: str
    cron_expression: str
    enabled: bool


class DLQRetryRequest(BaseModel):
    execution_id: str


class DLQRetryResponse(BaseModel):
    original_execution_id: str
    new_execution_id: str


class TradeResponse(BaseModel):
    trade_id: str
    symbol: str
    trade_date: date
    price: Decimal
    size: Decimal
    side: str
    venue: str | None


class MetricsResponse(BaseModel):
    symbol: str
    date: date
    vwap: Decimal
    total_volume: Decimal
    trade_count: int


# =============================================================================
# Health
# =============================================================================


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        version="0.3.0",
        backend=settings.backend_type,
    )


# =============================================================================
# Pipelines
# =============================================================================


@app.get("/pipelines", response_model=list[PipelineInfo])
async def list_pipelines():
    """List all registered pipelines."""
    return PipelineRegistry.list_pipelines()


@app.post("/pipelines/submit", response_model=SubmitResponse)
async def submit_pipeline(request: SubmitRequest):
    """Submit a pipeline for execution."""
    try:
        execution_id = Dispatcher.submit(
            pipeline_name=request.pipeline_name,
            params=request.params,
            max_retries=request.max_retries,
            skip_dedup=request.skip_dedup,
        )
        return SubmitResponse(
            execution_id=execution_id,
            pipeline_name=request.pipeline_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


# =============================================================================
# Executions
# =============================================================================


@app.get("/executions", response_model=list[ExecutionResponse])
async def list_executions(
    status: str | None = Query(None),
    pipeline_name: str | None = Query(None),
    limit: int = Query(100, le=1000),
):
    """List executions with optional filters."""
    executions = Dispatcher.list_executions(status, pipeline_name, limit)
    return executions


@app.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: str):
    """Get execution details."""
    execution = Dispatcher.get_status(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@app.get("/executions/{execution_id}/events")
async def get_execution_events(execution_id: str):
    """Get events for an execution."""
    events = ExecutionEventRepository.get_events(execution_id)
    return events


@app.get("/executions/{execution_id}/chain")
async def get_execution_chain(execution_id: str):
    """Get the retry chain for an execution."""
    chain = ExecutionRepository.get_execution_chain(execution_id)
    return chain


@app.post("/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str):
    """Cancel a pending/queued execution."""
    success = Dispatcher.cancel(execution_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel execution")
    return {"status": "cancelled"}


# =============================================================================
# DLQ
# =============================================================================


@app.get("/dlq")
async def list_dlq(
    limit: int = Query(100, le=1000),
    retryable_only: bool = Query(False),
):
    """List DLQ items."""
    if retryable_only:
        items = DLQManager.get_retryable(limit=limit)
    else:
        items = DLQManager.list_dlq(limit=limit)
    return items


@app.post("/dlq/retry", response_model=DLQRetryResponse)
async def retry_dlq(request: DLQRetryRequest):
    """Retry a DLQ item."""
    try:
        new_execution_id = DLQManager.retry(request.execution_id)
        if not new_execution_id:
            raise HTTPException(status_code=400, detail="Cannot retry execution")
        return DLQRetryResponse(
            original_execution_id=request.execution_id,
            new_execution_id=new_execution_id,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Schedules
# =============================================================================


@app.get("/schedules")
async def list_schedules(enabled_only: bool = Query(False)):
    """List pipeline schedules."""
    schedules = ScheduleManager.list_schedules(enabled_only)
    return schedules


@app.post("/schedules", response_model=ScheduleResponse)
async def create_schedule(request: ScheduleRequest):
    """Create a new pipeline schedule."""
    try:
        schedule_id = ScheduleManager.create_schedule(
            pipeline_name=request.pipeline_name,
            cron_expression=request.cron_expression,
            params=request.params,
        )
        return ScheduleResponse(
            id=schedule_id,
            pipeline_name=request.pipeline_name,
            cron_expression=request.cron_expression,
            enabled=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete a schedule."""
    success = ScheduleManager.delete_schedule(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted"}


@app.post("/schedules/{schedule_id}/enable")
async def enable_schedule(schedule_id: str):
    """Enable a schedule."""
    success = ScheduleManager.enable_schedule(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "enabled"}


@app.post("/schedules/{schedule_id}/disable")
async def disable_schedule(schedule_id: str):
    """Disable a schedule."""
    success = ScheduleManager.disable_schedule(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "disabled"}
