"""
Pipeline endpoints.

Provides endpoints for listing, describing, and executing pipelines.
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from market_spine.app.commands.executions import RunPipelineCommand, RunPipelineRequest
from market_spine.app.commands.pipelines import (
    DescribePipelineCommand,
    DescribePipelineRequest,
    ListPipelinesCommand,
    ListPipelinesRequest,
)
from market_spine.app.commands.queries import (
    QuerySymbolHistoryCommand,
    QuerySymbolHistoryRequest,
    QuerySymbolsCommand,
    QuerySymbolsRequest,
    QueryWeeksCommand,
    QueryWeeksRequest,
)
from market_spine.app.models import ErrorCode

# =============================================================================
# Response Models
# =============================================================================


class PipelineSummaryResponse(BaseModel):
    """Summary of a pipeline."""

    name: str
    description: str


class ListPipelinesResponse(BaseModel):
    """Response from listing pipelines."""

    pipelines: list[PipelineSummaryResponse]
    count: int


class ParameterDefResponse(BaseModel):
    """Definition of a pipeline parameter."""

    name: str
    type: str
    description: str
    default: Any = None
    required: bool = True
    choices: list[str] | None = None


class PipelineDetailResponse(BaseModel):
    """Detailed pipeline information."""

    name: str
    description: str
    required_params: list[ParameterDefResponse]
    optional_params: list[ParameterDefResponse]
    is_ingest: bool


class ExecutionResponse(BaseModel):
    """
    Response from pipeline execution.

    Reserved fields (execution_id, status, poll_url) are ALWAYS present.
    In Basic tier:
    - execution_id: UUID (from framework or generated)
    - status: "completed", "failed", or "dry_run"
    - poll_url: always null (no async execution)
    """

    execution_id: str = Field(description="Unique execution identifier (UUID)")
    pipeline: str = Field(description="Pipeline that was executed")
    status: str = Field(description="Execution status: completed, failed, dry_run")
    rows_processed: int | None = Field(
        default=None, description="Number of rows processed (if applicable)"
    )
    duration_seconds: float | None = Field(
        default=None, description="Execution duration in seconds"
    )
    # Reserved for future tiers - always present, null in Basic
    poll_url: str | None = Field(
        default=None,
        description="URL to poll for status (null in Basic tier, used in Intermediate+)",
    )


class WeekInfoResponse(BaseModel):
    """Information about an available week."""

    week_ending: str
    symbol_count: int


class QueryWeeksResponse(BaseModel):
    """Response from querying weeks."""

    tier: str
    weeks: list[WeekInfoResponse]
    count: int


class SymbolInfoResponse(BaseModel):
    """Information about a symbol."""

    symbol: str
    volume: int
    avg_price: float | None = None


class QuerySymbolsResponse(BaseModel):
    """Response from querying symbols."""

    tier: str
    week: str
    symbols: list[SymbolInfoResponse]
    count: int


class SymbolWeekDataResponse(BaseModel):
    """Trading data for a symbol in a specific week."""

    week_ending: str
    total_shares: int
    total_trades: int
    average_price: float | None = None


class QuerySymbolHistoryResponse(BaseModel):
    """Response from querying symbol history."""

    symbol: str
    tier: str
    history: list[SymbolWeekDataResponse]
    count: int


class RunPipelineBody(BaseModel):
    """Request body for running a pipeline."""

    params: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    lane: str = "default"


class ErrorResponse(BaseModel):
    """Standard error response."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Router
# =============================================================================

router = APIRouter(tags=["Pipelines"])


@router.get("/pipelines", response_model=ListPipelinesResponse)
async def list_pipelines(
    prefix: str | None = Query(None, description="Filter by pipeline name prefix"),
) -> ListPipelinesResponse:
    """
    List available pipelines.

    Optionally filter by name prefix (e.g., "finra" to list all FINRA pipelines).
    """
    command = ListPipelinesCommand()
    result = command.execute(ListPipelinesRequest(prefix=prefix))

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": {
                    "code": result.error.code.value,
                    "message": result.error.message,
                },
            },
        )

    return ListPipelinesResponse(
        pipelines=[
            PipelineSummaryResponse(name=p.name, description=p.description)
            for p in result.pipelines
        ],
        count=len(result.pipelines),
    )


@router.get("/pipelines/{pipeline_name:path}", response_model=PipelineDetailResponse)
async def describe_pipeline(pipeline_name: str) -> PipelineDetailResponse:
    """
    Get detailed information about a pipeline.

    Returns parameter definitions, whether it's an ingest pipeline, etc.
    """
    command = DescribePipelineCommand()
    result = command.execute(DescribePipelineRequest(name=pipeline_name))

    if not result.success:
        status_code = 404 if result.error.code == ErrorCode.PIPELINE_NOT_FOUND else 500
        raise HTTPException(
            status_code=status_code,
            detail={
                "success": False,
                "error": {
                    "code": result.error.code.value,
                    "message": result.error.message,
                },
            },
        )

    pipeline = result.pipeline
    return PipelineDetailResponse(
        name=pipeline.name,
        description=pipeline.description,
        required_params=[ParameterDefResponse(**p.__dict__) for p in pipeline.required_params],
        optional_params=[ParameterDefResponse(**p.__dict__) for p in pipeline.optional_params],
        is_ingest=pipeline.is_ingest,
    )


@router.post("/pipelines/{pipeline_name:path}/run", response_model=ExecutionResponse)
async def run_pipeline(
    pipeline_name: str,
    body: RunPipelineBody,
) -> ExecutionResponse:
    """
    Execute a pipeline.

    In Basic tier, execution is synchronous and blocks until completion.
    The response includes execution metrics.

    Use dry_run=true to validate parameters without executing.
    """
    # Map lane string to canonical value (no framework import needed)
    lane_map = {
        "default": "normal",
        "normal": "normal",
        "backfill": "backfill",
        "slow": "slow",
    }
    lane = lane_map.get(body.lane.lower(), "normal")

    command = RunPipelineCommand()
    result = command.execute(
        RunPipelineRequest(
            pipeline=pipeline_name,
            params=body.params,
            lane=lane,
            dry_run=body.dry_run,
            trigger_source="api",
        )
    )

    if not result.success:
        if result.error.code == ErrorCode.PIPELINE_NOT_FOUND:
            status_code = 404
        elif result.error.code in (
            ErrorCode.INVALID_PARAMS,
            ErrorCode.INVALID_TIER,
            ErrorCode.INVALID_DATE,
            ErrorCode.MISSING_REQUIRED,
        ):
            status_code = 400
        else:
            status_code = 500
        raise HTTPException(
            status_code=status_code,
            detail={
                "success": False,
                "error": {
                    "code": result.error.code.value,
                    "message": result.error.message,
                },
            },
        )

    # Ensure execution_id is always present (generate if not provided)
    execution_id = result.execution_id or str(uuid.uuid4())

    return ExecutionResponse(
        execution_id=execution_id,
        pipeline=pipeline_name,
        status=result.status.value if result.status else "completed",
        rows_processed=result.metrics.rows_processed if result.metrics else None,
        duration_seconds=result.metrics.duration_seconds if result.metrics else None,
        poll_url=None,  # Always null in Basic tier
    )


@router.get("/data/weeks", response_model=QueryWeeksResponse)
async def list_weeks(
    tier: str = Query(..., description="Tier: OTC, NMS_TIER_1, NMS_TIER_2"),
    limit: int = Query(10, ge=1, le=100, description="Max weeks to return"),
) -> QueryWeeksResponse:
    """
    List available weeks of data for a tier.

    Returns the most recent weeks with symbol counts.
    """
    command = QueryWeeksCommand()
    result = command.execute(QueryWeeksRequest(tier=tier, limit=limit))

    if not result.success:
        status_code = 400 if result.error.code == ErrorCode.INVALID_TIER else 500
        raise HTTPException(
            status_code=status_code,
            detail={
                "success": False,
                "error": {
                    "code": result.error.code.value,
                    "message": result.error.message,
                },
            },
        )

    return QueryWeeksResponse(
        tier=result.tier,
        weeks=[
            WeekInfoResponse(week_ending=w.week_ending, symbol_count=w.symbol_count)
            for w in result.weeks
        ],
        count=result.count,
    )


@router.get("/data/symbols", response_model=QuerySymbolsResponse)
async def list_symbols(
    tier: str = Query(..., description="Tier: OTC, NMS_TIER_1, NMS_TIER_2"),
    week: str = Query(..., description="Week ending date (YYYY-MM-DD)"),
    top: int = Query(10, ge=1, le=100, description="Number of top symbols to return"),
) -> QuerySymbolsResponse:
    """
    List top symbols by volume for a specific week.

    Returns symbols sorted by total trading volume.
    """
    command = QuerySymbolsCommand()
    result = command.execute(QuerySymbolsRequest(tier=tier, week=week, top=top))

    if not result.success:
        status_code = (
            400 if result.error.code in (ErrorCode.INVALID_TIER, ErrorCode.INVALID_DATE) else 500
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "success": False,
                "error": {
                    "code": result.error.code.value,
                    "message": result.error.message,
                },
            },
        )

    return QuerySymbolsResponse(
        tier=result.tier,
        week=result.week,
        symbols=[
            SymbolInfoResponse(symbol=s.symbol, volume=s.volume, avg_price=s.avg_price)
            for s in result.symbols
        ],
        count=result.count,
    )


@router.get("/data/symbols/{symbol}/history", response_model=QuerySymbolHistoryResponse)
async def get_symbol_history(
    symbol: str,
    tier: str = Query(..., description="Tier: OTC, NMS_TIER_1, NMS_TIER_2"),
    weeks: int = Query(12, ge=1, le=52, description="Number of weeks of history"),
) -> QuerySymbolHistoryResponse:
    """
    Get historical trading data for a specific symbol.

    Returns weekly trading data sorted chronologically (oldest to newest)
    for charting purposes.
    """
    command = QuerySymbolHistoryCommand()
    result = command.execute(QuerySymbolHistoryRequest(symbol=symbol, tier=tier, weeks=weeks))

    if not result.success:
        status_code = (
            400
            if result.error.code in (ErrorCode.INVALID_TIER, ErrorCode.MISSING_REQUIRED)
            else 500
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "success": False,
                "error": {
                    "code": result.error.code.value,
                    "message": result.error.message,
                },
            },
        )

    return QuerySymbolHistoryResponse(
        symbol=result.symbol,
        tier=result.tier,
        history=[
            SymbolWeekDataResponse(
                week_ending=h.week_ending,
                total_shares=h.total_shares,
                total_trades=h.total_trades,
                average_price=h.average_price,
            )
            for h in result.history
        ],
        count=result.count,
    )
