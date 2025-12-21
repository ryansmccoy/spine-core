"""Schedule management MCP tools."""

from __future__ import annotations

from typing import Any

from spine.mcp import _app

mcp = _app.mcp


@mcp.tool()
async def list_schedules(limit: int = 50) -> dict[str, Any]:
    """List all configured schedules.

    Args:
        limit: Maximum number of schedules to return

    Returns:
        Dictionary with 'schedules' list
    """
    from spine.ops.context import OperationContext
    from spine.ops.schedules import list_schedules as _list_schedules

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "schedules": []}

    result = _list_schedules(OperationContext(conn=ctx.conn))

    return {
        "schedules": [
            {
                "schedule_id": s.schedule_id,
                "name": s.name,
                "target_type": s.target_type,
                "target_name": s.target_name,
                "cron_expression": s.cron_expression,
                "enabled": s.enabled,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
            }
            for s in result.items[:limit]
        ],
        "total": result.total,
    }


@mcp.tool()
async def create_schedule(
    name: str,
    target_name: str,
    cron_expression: str | None = None,
    interval_seconds: int | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Create a new schedule.

    Args:
        name: Schedule name
        target_name: Workflow or operation to execute
        cron_expression: Cron expression (e.g., '0 */4 * * *')
        interval_seconds: Alternative to cron, interval in seconds
        enabled: Whether schedule is active

    Returns:
        Dictionary with schedule_id
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import CreateScheduleRequest
    from spine.ops.schedules import create_schedule as _create_schedule

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = CreateScheduleRequest(
        name=name,
        target_name=target_name,
        cron_expression=cron_expression,
        interval_seconds=interval_seconds,
        enabled=enabled,
    )

    result = _create_schedule(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return {"schedule_id": result.data.schedule_id, "created": True}


@mcp.tool()
async def get_schedule(schedule_id: str) -> dict[str, Any]:
    """Get detailed information about a specific schedule.

    Args:
        schedule_id: Unique schedule identifier

    Returns:
        Schedule details including target, cron expression, and enabled status
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import GetScheduleRequest
    from spine.ops.schedules import get_schedule as _get_schedule

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = GetScheduleRequest(schedule_id=schedule_id)
    result = _get_schedule(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    s = result.data
    return {
        "schedule_id": s.schedule_id,
        "name": s.name,
        "target_type": s.target_type,
        "target_name": s.target_name,
        "cron_expression": s.cron_expression,
        "interval_seconds": s.interval_seconds,
        "enabled": s.enabled,
    }


@mcp.tool()
async def update_schedule(
    schedule_id: str,
    name: str | None = None,
    target_name: str | None = None,
    cron_expression: str | None = None,
    interval_seconds: int | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Update an existing schedule.

    Only provided fields are updated; omitted fields retain their
    current values.

    Args:
        schedule_id: Unique schedule identifier
        name: New schedule name
        target_name: New workflow or operation to execute
        cron_expression: New cron expression
        interval_seconds: New interval in seconds
        enabled: Enable or disable the schedule

    Returns:
        Updated schedule details
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import UpdateScheduleRequest
    from spine.ops.schedules import update_schedule as _update_schedule

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = UpdateScheduleRequest(
        schedule_id=schedule_id,
        name=name,
        target_name=target_name,
        cron_expression=cron_expression,
        interval_seconds=interval_seconds,
        enabled=enabled,
    )
    result = _update_schedule(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    s = result.data
    return {
        "schedule_id": s.schedule_id,
        "name": s.name,
        "target_type": s.target_type,
        "target_name": s.target_name,
        "cron_expression": s.cron_expression,
        "interval_seconds": s.interval_seconds,
        "enabled": s.enabled,
        "updated": True,
    }


@mcp.tool()
async def delete_schedule(schedule_id: str) -> dict[str, Any]:
    """Delete a schedule.

    Permanently removes the schedule configuration. Active runs
    triggered by this schedule are not affected.

    Args:
        schedule_id: Unique schedule identifier

    Returns:
        Confirmation of deletion
    """
    from spine.ops.context import OperationContext
    from spine.ops.requests import DeleteScheduleRequest
    from spine.ops.schedules import delete_schedule as _delete_schedule

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = DeleteScheduleRequest(schedule_id=schedule_id)
    result = _delete_schedule(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return {"deleted": True, "schedule_id": schedule_id}
