"""
CLI: ``spine-core runs`` — execution run management commands.
"""

from __future__ import annotations

import typer

from spine.cli.utils import console, make_context, output_paged, output_result

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_runs(
    kind: str | None = typer.Option(None, "--kind", "-k"),
    status: str | None = typer.Option(None, "--status", "-s"),
    workflow: str | None = typer.Option(None, "--workflow", "-w"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List execution runs with filtering."""
    from spine.ops.requests import ListRunsRequest
    from spine.ops.runs import list_runs as _list

    ctx, _ = make_context(database)
    request = ListRunsRequest(
        kind=kind, status=status,
        workflow=workflow, limit=limit, offset=offset,
    )
    result = _list(ctx, request)
    output_paged(result, as_json=json_out, title="Runs")


@app.command("show")
def show_run(
    run_id: str = typer.Argument(..., help="Run ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show detailed information about a run."""
    from spine.ops.requests import GetRunRequest
    from spine.ops.runs import get_run as _get

    ctx, _ = make_context(database)
    result = _get(ctx, GetRunRequest(run_id=run_id))
    output_result(result, as_json=json_out, title=f"Run: {run_id}")


@app.command()
def cancel(
    run_id: str = typer.Argument(..., help="Run ID"),
    reason: str = typer.Option("", "--reason", "-r"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Cancel a running execution."""
    from spine.ops.requests import CancelRunRequest
    from spine.ops.runs import cancel_run as _cancel

    ctx, _ = make_context(database)
    result = _cancel(ctx, CancelRunRequest(run_id=run_id, reason=reason))
    output_result(result, as_json=json_out, title="Cancel")


@app.command()
def retry(
    run_id: str = typer.Argument(..., help="Run ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Retry a failed execution."""
    from spine.ops.requests import RetryRunRequest
    from spine.ops.runs import retry_run as _retry

    ctx, _ = make_context(database)
    result = _retry(ctx, RetryRunRequest(run_id=run_id))
    output_result(result, as_json=json_out, title="Retry")


@app.command()
def submit(
    name: str = typer.Argument(..., help="Name of task, operation, or workflow"),
    kind: str = typer.Option("operation", "--kind", "-k", help="Run kind: task, operation, or workflow"),
    params: str | None = typer.Option(None, "--params", "-p", help="JSON params string"),
    priority: str = typer.Option("default", "--priority", help="Execution priority lane"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without executing"),
) -> None:
    """Submit a new execution run (task, operation, or workflow)."""
    import json as _json

    from spine.ops.requests import SubmitRunRequest
    from spine.ops.runs import submit_run as _submit

    ctx, _ = make_context(database)
    if dry_run:
        ctx = ctx._replace(dry_run=True) if hasattr(ctx, '_replace') else ctx

    parsed_params = None
    if params:
        try:
            parsed_params = _json.loads(params)
        except _json.JSONDecodeError as e:
            console.print(f"[red]Error: Invalid JSON params: {e}[/red]")
            raise typer.Exit(1) from e

    request = SubmitRunRequest(name=name, kind=kind, params=parsed_params, priority=priority)
    result = _submit(ctx, request)
    output_result(result, as_json=json_out, title="Submit")


@app.command()
def events(
    run_id: str = typer.Argument(..., help="Run ID"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List events for a run (event-sourced history)."""
    from spine.ops.requests import GetRunEventsRequest
    from spine.ops.runs import get_run_events as _events

    ctx, _ = make_context(database)
    request = GetRunEventsRequest(run_id=run_id, limit=limit, offset=offset)
    result = _events(ctx, request)
    output_paged(result, as_json=json_out, title=f"Events for {run_id}")
