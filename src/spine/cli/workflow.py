"""
CLI: ``spine-core workflow`` — workflow management commands.
"""

from __future__ import annotations

import typer

from spine.cli.utils import make_context, output_paged, output_result

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_workflows(
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List all registered workflows."""
    from spine.ops.workflows import list_workflows as _list

    ctx, _ = make_context(database)
    result = _list(ctx)
    output_paged(result, as_json=json_out, title="Workflows")


@app.command("show")
def show_workflow(
    name: str = typer.Argument(..., help="Workflow name"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show workflow details and step graph."""
    from spine.ops.requests import GetWorkflowRequest
    from spine.ops.workflows import get_workflow as _get

    ctx, _ = make_context(database)
    result = _get(ctx, GetWorkflowRequest(name=name))
    output_result(result, as_json=json_out, title=f"Workflow: {name}")


@app.command("run")
def run_workflow(
    name: str = typer.Argument(..., help="Workflow name"),
    database: str | None = typer.Option(None, "--database", "-d"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_out: bool = typer.Option(False, "--json"),
    idempotency_key: str = typer.Option("", "--key", help="Idempotency key"),
) -> None:
    """Trigger a workflow execution."""
    from spine.ops.requests import RunWorkflowRequest
    from spine.ops.workflows import run_workflow as _run

    ctx, _ = make_context(database, dry_run=dry_run)
    request = RunWorkflowRequest(name=name, idempotency_key=idempotency_key)
    result = _run(ctx, request)
    output_result(result, as_json=json_out, title="Run Accepted")
