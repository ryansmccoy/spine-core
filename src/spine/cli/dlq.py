"""
CLI: ``spine-core dlq`` — dead-letter queue commands.
"""

from __future__ import annotations

import typer

from spine.cli.utils import make_context, output_paged, output_result

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_dead_letters(
    workflow: str | None = typer.Option(None, "--workflow", "-w"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List dead-letter entries."""
    from spine.ops.dlq import list_dead_letters as _list
    from spine.ops.requests import ListDeadLettersRequest

    ctx, _ = make_context(database)
    request = ListDeadLettersRequest(workflow=workflow, limit=limit, offset=offset)
    result = _list(ctx, request)
    output_paged(result, as_json=json_out, title="Dead Letters")


@app.command("replay")
def replay(
    dead_letter_id: str = typer.Argument(..., help="Dead-letter entry ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Replay a dead-letter entry."""
    from spine.ops.dlq import replay_dead_letter as _replay
    from spine.ops.requests import ReplayDeadLetterRequest

    ctx, _ = make_context(database)
    result = _replay(ctx, ReplayDeadLetterRequest(dead_letter_id=dead_letter_id))
    output_result(result, as_json=json_out, title="Replay")
