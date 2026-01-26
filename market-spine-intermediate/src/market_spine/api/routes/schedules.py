"""Schedule management endpoints.

Provides API access to schedule definitions and execution history.

Follows API Design Guardrails:
- Resource-style URLs: /v1/schedules, /v1/schedules/{id}/runs
- Pagination: offset/limit with has_more
- Standard error envelope
"""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================


class PaginationMeta(BaseModel):
    """Standard pagination metadata."""
    offset: int
    limit: int
    total: int
    has_more: bool


class ScheduleCreate(BaseModel):
    """Request to create a schedule."""
    name: str = Field(..., description="Unique schedule name")
    target_type: Literal["pipeline", "workflow"] = Field("pipeline", description="Target type")
    target_name: str = Field(..., description="Pipeline or workflow name")
    params: dict[str, Any] = Field(default_factory=dict, description="Default parameters")
    
    # Schedule specification
    schedule_type: Literal["cron", "interval"] = Field("cron", description="Schedule type")
    cron_expression: str | None = Field(None, description="Cron expression (e.g., '0 6 * * 1-5')")
    interval_seconds: int | None = Field(None, description="Interval in seconds")
    timezone: str = Field("UTC", description="Timezone for schedule")
    
    # Control
    enabled: bool = Field(True, description="Whether schedule is active")
    max_instances: int = Field(1, description="Max concurrent runs")


class ScheduleUpdate(BaseModel):
    """Request to update a schedule."""
    params: dict[str, Any] | None = None
    cron_expression: str | None = None
    interval_seconds: int | None = None
    timezone: str | None = None
    enabled: bool | None = None
    max_instances: int | None = None


class ScheduleResponse(BaseModel):
    """Schedule details."""
    id: str
    name: str
    target_type: str
    target_name: str
    params: dict[str, Any] | None
    
    # Schedule
    schedule_type: str
    cron_expression: str | None
    interval_seconds: int | None
    timezone: str
    
    # State
    enabled: bool
    max_instances: int
    
    # Timing
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_run_status: str | None
    
    # Audit
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    version: int

    model_config = {"from_attributes": True}


class ScheduleList(BaseModel):
    """Paginated list of schedules."""
    data: list[ScheduleResponse]
    pagination: PaginationMeta


class ScheduleRunSummary(BaseModel):
    """Summary of a scheduled run."""
    id: str
    schedule_id: str
    schedule_name: str
    scheduled_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED", "MISSED"]
    run_id: str | None
    error: str | None
    skip_reason: str | None

    model_config = {"from_attributes": True}


class ScheduleRunList(BaseModel):
    """Paginated list of schedule runs."""
    data: list[ScheduleRunSummary]
    pagination: PaginationMeta


class ScheduleActionResponse(BaseModel):
    """Response for schedule actions."""
    id: str
    status: str
    message: str


class NextRunsResponse(BaseModel):
    """Upcoming scheduled runs."""
    schedule_id: str
    schedule_name: str
    next_runs: list[datetime]


# =============================================================================
# SCHEDULE MANAGEMENT ENDPOINTS
# =============================================================================


@router.get(
    "",
    response_model=ScheduleList,
    summary="List schedules",
    description="Get paginated list of schedule definitions",
)
async def list_schedules(
    target_type: str | None = Query(None, description="Filter by target type"),
    target_name: str | None = Query(None, description="Filter by target name"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """
    List all schedule definitions.
    
    Use filters to narrow results by target or status.
    """
    # TODO: Implement with ScheduleRepository
    return ScheduleList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )


@router.post(
    "",
    response_model=ScheduleResponse,
    status_code=201,
    summary="Create schedule",
    description="Create a new schedule definition",
)
async def create_schedule(request: ScheduleCreate):
    """
    Create a new schedule.
    
    The schedule will be active immediately if enabled=true.
    Use cron_expression for cron schedules or interval_seconds for interval schedules.
    """
    # TODO: Implement with SchedulerService
    # 1. Validate cron expression or interval
    # 2. Validate target exists
    # 3. Create schedule record
    # 4. Register with scheduler
    raise HTTPException(
        status_code=501,
        detail={"code": "NOT_IMPLEMENTED", "message": "Schedule creation not yet implemented"},
    )


@router.get(
    "/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Get schedule",
    description="Get schedule details",
)
async def get_schedule(
    schedule_id: str = Path(..., description="Schedule ID"),
):
    """Get details of a specific schedule."""
    # TODO: Implement with ScheduleRepository
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Schedule not found: {schedule_id}"},
    )


@router.patch(
    "/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Update schedule",
    description="Update schedule configuration",
)
async def update_schedule(
    schedule_id: str = Path(..., description="Schedule ID"),
    request: ScheduleUpdate = ...,
):
    """
    Update an existing schedule.
    
    Only provided fields will be updated.
    """
    # TODO: Implement with SchedulerService
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Schedule not found: {schedule_id}"},
    )


@router.delete(
    "/{schedule_id}",
    status_code=204,
    summary="Delete schedule",
    description="Delete a schedule",
)
async def delete_schedule(
    schedule_id: str = Path(..., description="Schedule ID"),
):
    """
    Delete a schedule.
    
    This stops future executions but does not affect runs in progress.
    """
    # TODO: Implement with SchedulerService
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Schedule not found: {schedule_id}"},
    )


# =============================================================================
# SCHEDULE CONTROL ENDPOINTS
# =============================================================================


@router.post(
    "/{schedule_id}/enable",
    response_model=ScheduleActionResponse,
    summary="Enable schedule",
    description="Enable a disabled schedule",
)
async def enable_schedule(
    schedule_id: str = Path(..., description="Schedule ID"),
):
    """Enable a schedule for execution."""
    # TODO: Implement
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Schedule not found: {schedule_id}"},
    )


@router.post(
    "/{schedule_id}/disable",
    response_model=ScheduleActionResponse,
    summary="Disable schedule",
    description="Disable a schedule",
)
async def disable_schedule(
    schedule_id: str = Path(..., description="Schedule ID"),
):
    """Disable a schedule to stop executions."""
    # TODO: Implement
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Schedule not found: {schedule_id}"},
    )


@router.post(
    "/{schedule_id}/run-now",
    response_model=ScheduleActionResponse,
    status_code=202,
    summary="Run schedule now",
    description="Trigger immediate execution of a schedule",
)
async def run_schedule_now(
    schedule_id: str = Path(..., description="Schedule ID"),
    params: dict[str, Any] | None = None,
):
    """
    Trigger immediate execution of a schedule.
    
    This runs the schedule's target with optional parameter overrides.
    Does not affect the normal schedule.
    """
    # TODO: Implement with SchedulerService
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Schedule not found: {schedule_id}"},
    )


@router.get(
    "/{schedule_id}/next-runs",
    response_model=NextRunsResponse,
    summary="Get next runs",
    description="Preview upcoming scheduled runs",
)
async def get_next_runs(
    schedule_id: str = Path(..., description="Schedule ID"),
    count: int = Query(5, ge=1, le=20, description="Number of runs to preview"),
):
    """
    Preview the next N scheduled execution times.
    
    Useful for verifying cron expressions.
    """
    # TODO: Implement with cron parsing
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Schedule not found: {schedule_id}"},
    )


# =============================================================================
# SCHEDULE RUN HISTORY
# =============================================================================


@router.get(
    "/{schedule_id}/runs",
    response_model=ScheduleRunList,
    summary="List schedule runs",
    description="Get execution history for a schedule",
)
async def list_schedule_runs(
    schedule_id: str = Path(..., description="Schedule ID"),
    status: str | None = Query(None, description="Filter by status"),
    start_date: str | None = Query(None, description="Filter by date range start"),
    end_date: str | None = Query(None, description="Filter by date range end"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """
    Get execution history for a schedule.
    
    Shows when the schedule ran and the result of each run.
    """
    # TODO: Implement with ScheduleRunRepository
    return ScheduleRunList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )


@router.get(
    "/runs/all",
    response_model=ScheduleRunList,
    summary="List all schedule runs",
    description="Get execution history across all schedules",
)
async def list_all_schedule_runs(
    schedule_name: str | None = Query(None, description="Filter by schedule name"),
    status: str | None = Query(None, description="Filter by status"),
    start_date: str | None = Query(None, description="Filter by date range start"),
    end_date: str | None = Query(None, description="Filter by date range end"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """
    Get execution history across all schedules.
    
    Useful for operational dashboards.
    """
    # TODO: Implement with ScheduleRunRepository
    return ScheduleRunList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )
