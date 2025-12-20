"""
CLI: ``spine-core quality`` — quality check results commands.
"""

from __future__ import annotations

import typer

from spine.cli.utils import make_context, output_paged

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_quality_results(
    workflow: str | None = typer.Option(None, "--workflow", "-w"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List quality check results."""
    from spine.ops.quality import list_quality_results as _list
    from spine.ops.requests import ListQualityResultsRequest

    ctx, _ = make_context(database)
    request = ListQualityResultsRequest(workflow=workflow, limit=limit, offset=offset)
    result = _list(ctx, request)
    output_paged(result, as_json=json_out, title="Quality Results")
