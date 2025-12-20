"""
Schedule router — CRUD for workflow schedules.

GET    /schedules
GET    /schedules/{schedule_id}
POST   /schedules
PUT    /schedules/{schedule_id}
DELETE /schedules/{schedule_id}
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field

from spine.api.deps import OpContext
from spine.api.schemas.common import PagedResponse, PageMeta, SuccessResponse
from spine.api.schemas.domains import ScheduleDetailSchema, ScheduleSummarySchema
from spine.api.utils import _dc, _handle_error

router = APIRouter(prefix="/schedules")


class CreateScheduleBody(BaseModel):
    name: str = ""
    target_type: str = "pipeline"
    target_name: str = ""
    cron_expression: str = ""
    interval_seconds: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class UpdateScheduleBody(BaseModel):
    name: str | None = None
    target_name: str | None = None
    cron_expression: str | None = None
    interval_seconds: int | None = None
    enabled: bool | None = None
    params: dict[str, Any] | None = None


@router.get("", response_model=PagedResponse[ScheduleSummarySchema])
def list_schedules(ctx: OpContext):
    """List all workflow schedules.

    Returns all configured schedules with their status and next run time.
    Use for the Schedules management view in the orchestration console.

    Args:
        ctx: Operation context with database connection.

    Returns:
        PagedResponse containing list of ScheduleSummarySchema items.

    Example:
        GET /api/v1/schedules

        Response:
        {
            "data": [
                {
                    "schedule_id": "sched-123",
                    "workflow_name": "daily_etl",
                    "cron": "0 9 * * *",
                    "enabled": true,
                    "next_run": "2026-02-14T09:00:00Z"
                }
            ],
            "page": {"total": 1, "limit": 50, "offset": 0, "has_more": false}
        }
    """
    from spine.ops.schedules import list_schedules as _list

    result = _list(ctx)
    if not result.success:
        return _handle_error(result)
    items = [ScheduleSummarySchema(**_dc(s)) for s in (result.data or [])]
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


@router.get("/{schedule_id}", response_model=SuccessResponse[ScheduleDetailSchema])
def get_schedule(ctx: OpContext, schedule_id: str = Path(..., description="Schedule ID")):
    """Get schedule details.

    Returns full schedule configuration including execution history stats.
    Use for schedule detail views and edit forms.

    Args:
        ctx: Operation context with database connection.
        schedule_id: The unique schedule identifier.

    Returns:
        SuccessResponse containing ScheduleDetailSchema.

    Raises:
        404 NOT_FOUND: Schedule with specified ID does not exist.

    Example:
        GET /api/v1/schedules/sched-123

        Response:
        {
            "data": {
                "schedule_id": "sched-123",
                "workflow_name": "daily_etl",
                "cron": "0 9 * * *",
                "params": {"mode": "incremental"},
                "enabled": true,
                "last_run": "2026-02-13T09:00:00Z",
                "run_count": 42
            }
        }
    """
    from spine.ops.requests import GetScheduleRequest
    from spine.ops.schedules import get_schedule as _get

    result = _get(ctx, GetScheduleRequest(schedule_id=schedule_id))
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=ScheduleDetailSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.post("", response_model=SuccessResponse[ScheduleDetailSchema], status_code=201)
def create_schedule(ctx: OpContext, body: CreateScheduleBody):
    """Create a new schedule.

    Creates a scheduled trigger for a workflow. The schedule becomes
    active immediately if ``enabled=true``.

    Args:
        ctx: Operation context with database connection.
        body: Schedule configuration.

    Returns:
        SuccessResponse containing the created ScheduleDetailSchema.
        Status code 201 indicates successful creation.

    Raises:
        400 VALIDATION_FAILED: Invalid cron expression or missing workflow_name.
        404 NOT_FOUND: Referenced workflow does not exist.

    Example:
        POST /api/v1/schedules
        {"workflow_name": "daily_etl", "cron": "0 9 * * *"}

        Response (201):
        {"data": {"schedule_id": "sched-456", "workflow_name": "daily_etl", ...}}
    """
    from spine.ops.requests import CreateScheduleRequest
    from spine.ops.schedules import create_schedule as _create

    request = CreateScheduleRequest(
        name=body.name,
        target_type=body.target_type,
        target_name=body.target_name,
        cron_expression=body.cron_expression,
        interval_seconds=body.interval_seconds,
        params=body.params,
        enabled=body.enabled,
    )
    result = _create(ctx, request)
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=ScheduleDetailSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.put("/{schedule_id}", response_model=SuccessResponse[ScheduleDetailSchema])
def update_schedule(
    ctx: OpContext,
    body: UpdateScheduleBody,
    schedule_id: str = Path(..., description="Schedule ID"),
):
    """Update an existing schedule.

    Updates schedule configuration. Only provided fields are changed.
    Use to enable/disable schedules or modify timing.

    Args:
        ctx: Operation context with database connection.
        body: Fields to update (partial update).
        schedule_id: The schedule to modify.

    Returns:
        SuccessResponse containing the updated ScheduleDetailSchema.

    Raises:
        404 NOT_FOUND: Schedule with specified ID does not exist.
        400 VALIDATION_FAILED: Invalid cron expression.

    Example:
        PUT /api/v1/schedules/sched-123
        {"enabled": false}

        Response:
        {"data": {"schedule_id": "sched-123", "enabled": false, ...}}
    """
    from spine.ops.requests import UpdateScheduleRequest
    from spine.ops.schedules import update_schedule as _update

    request = UpdateScheduleRequest(
        schedule_id=schedule_id,
        name=body.name,
        target_name=body.target_name,
        cron_expression=body.cron_expression,
        interval_seconds=body.interval_seconds,
        enabled=body.enabled,
        params=body.params,
    )
    result = _update(ctx, request)
    if not result.success:
        return _handle_error(result)
    return SuccessResponse(
        data=ScheduleDetailSchema(**_dc(result.data)),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(ctx: OpContext, schedule_id: str = Path(..., description="Schedule ID")):
    """Delete a schedule.

    Permanently removes a schedule. This does not affect runs that
    have already been triggered by this schedule.

    Args:
        ctx: Operation context with database connection.
        schedule_id: The schedule to delete.

    Returns:
        No content (204) on success.

    Raises:
        404 NOT_FOUND: Schedule with specified ID does not exist.

    Example:
        DELETE /api/v1/schedules/sched-123

        Response: 204 No Content
    """
    from spine.ops.requests import DeleteScheduleRequest
    from spine.ops.schedules import delete_schedule as _delete

    result = _delete(ctx, DeleteScheduleRequest(schedule_id=schedule_id))
    if not result.success:
        return _handle_error(result)
    return None
