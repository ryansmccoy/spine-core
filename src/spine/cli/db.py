"""
CLI: ``spine-core db`` — database management commands.
"""

from __future__ import annotations

import typer

from spine.cli.utils import make_context, output_result

app = typer.Typer(no_args_is_help=True)


@app.command()
def init(
    database: str | None = typer.Option(None, "--database", "-d", help="Database path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes"),
    json_out: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Initialise database schema (create tables)."""
    from spine.ops.database import initialize_database
    from spine.ops.requests import DatabaseInitRequest

    ctx, _conn = make_context(database, dry_run=dry_run)
    result = initialize_database(ctx, DatabaseInitRequest())
    output_result(result, as_json=json_out, title="Database Init")


@app.command()
def health(
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Check database connectivity and stats."""
    from spine.ops.database import check_database_health

    ctx, _conn = make_context(database)
    result = check_database_health(ctx)
    output_result(result, as_json=json_out, title="Database Health")


@app.command()
def tables(
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show row counts for all managed tables."""
    from spine.ops.database import get_table_counts

    ctx, _conn = make_context(database)
    result = get_table_counts(ctx)
    output_result(result, as_json=json_out, title="Table Counts")


@app.command()
def purge(
    older_than_days: int = typer.Option(90, "--days", help="Purge data older than N days"),
    database: str | None = typer.Option(None, "--database", "-d"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Purge old execution data."""
    from spine.ops.database import purge_old_data
    from spine.ops.requests import PurgeRequest

    ctx, _conn = make_context(database, dry_run=dry_run)
    result = purge_old_data(ctx, PurgeRequest(older_than_days=older_than_days))
    output_result(result, as_json=json_out, title="Purge Result")
