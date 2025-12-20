"""
CLI: ``spine-core health`` — health and capabilities commands.
"""

from __future__ import annotations

import typer

from spine.cli.utils import make_context, output_result

app = typer.Typer(no_args_is_help=True)


@app.command("check")
def health_check(
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Check system health."""
    from spine.ops.health import get_health

    ctx, _ = make_context(database)
    result = get_health(ctx)
    output_result(result, as_json=json_out, title="Health")


@app.command("capabilities")
def capabilities(
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show server capabilities."""
    from spine.ops.health import get_capabilities

    ctx, _ = make_context(database)
    result = get_capabilities(ctx)
    output_result(result, as_json=json_out, title="Capabilities")
