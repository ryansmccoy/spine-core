"""
CLI: ``spine-core schedule`` — schedule CRUD commands.
"""

from __future__ import annotations

import typer

from spine.cli.utils import make_context, output_paged, output_result

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_schedules(
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List all workflow schedules."""
    from spine.ops.schedules import list_schedules as _list

    ctx, _ = make_context(database)
    result = _list(ctx)
    output_paged(result, as_json=json_out, title="Schedules")


@app.command("show")
def show_schedule(
    schedule_id: str = typer.Argument(..., help="Schedule ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show schedule details."""
    from spine.ops.requests import GetScheduleRequest
    from spine.ops.schedules import get_schedule as _get

    ctx, _ = make_context(database)
    result = _get(ctx, GetScheduleRequest(schedule_id=schedule_id))
    output_result(result, as_json=json_out, title=f"Schedule: {schedule_id}")


@app.command("create")
def create_schedule(
    workflow_name: str = typer.Argument(..., help="Workflow to schedule"),
    cron: str = typer.Option("", "--cron", help="Cron expression"),
    interval: int | None = typer.Option(None, "--interval", help="Interval in seconds"),
    enabled: bool = typer.Option(True, "--enabled/--disabled"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Create a new schedule."""
    from spine.ops.requests import CreateScheduleRequest
    from spine.ops.schedules import create_schedule as _create

    ctx, _ = make_context(database)
    request = CreateScheduleRequest(
        workflow_name=workflow_name,
        cron=cron,
        interval_seconds=interval,
        enabled=enabled,
    )
    result = _create(ctx, request)
    output_result(result, as_json=json_out, title="Schedule Created")


@app.command("update")
def update_schedule(
    schedule_id: str = typer.Argument(..., help="Schedule ID"),
    cron: str | None = typer.Option(None, "--cron"),
    interval: int | None = typer.Option(None, "--interval"),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Update an existing schedule."""
    from spine.ops.requests import UpdateScheduleRequest
    from spine.ops.schedules import update_schedule as _update

    ctx, _ = make_context(database)
    request = UpdateScheduleRequest(
        schedule_id=schedule_id,
        cron=cron,
        interval_seconds=interval,
        enabled=enabled,
    )
    result = _update(ctx, request)
    output_result(result, as_json=json_out, title="Schedule Updated")


@app.command("delete")
def delete_schedule(
    schedule_id: str = typer.Argument(..., help="Schedule ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Delete a schedule."""
    from spine.ops.requests import DeleteScheduleRequest
    from spine.ops.schedules import delete_schedule as _delete

    ctx, _ = make_context(database)
    result = _delete(ctx, DeleteScheduleRequest(schedule_id=schedule_id))
    output_result(result, as_json=json_out, title="Schedule Deleted")
