"""
CLI: ``spine-core sources`` — data source and fetch management.
"""

from __future__ import annotations

import json

import typer

from spine.cli.utils import console, err_console, make_context, output_paged, output_result

app = typer.Typer(no_args_is_help=True)


# ------------------------------------------------------------------ #
# Sources Commands
# ------------------------------------------------------------------ #


@app.command("list")
def list_sources(
    source_type: str | None = typer.Option(None, "--type", "-t"),
    domain: str | None = typer.Option(None, "--domain"),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List registered data sources."""
    from spine.ops.requests import ListSourcesRequest
    from spine.ops.sources import list_sources as _list

    ctx, _ = make_context(database)
    request = ListSourcesRequest(
        source_type=source_type,
        domain=domain,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)
    output_paged(result, as_json=json_out, title="Sources")


@app.command("register")
def register_source(
    name: str = typer.Argument(..., help="Unique source name"),
    source_type: str = typer.Option("file", "--type", "-t", help="Source type: file, http, database, s3, sftp"),
    config: str = typer.Option("{}", "--config", "-c", help="JSON configuration"),
    domain: str | None = typer.Option(None, "--domain"),
    disabled: bool = typer.Option(False, "--disabled", help="Create disabled"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Register a new data source."""
    from spine.ops.requests import CreateSourceRequest
    from spine.ops.sources import register_source as _register

    try:
        config_dict = json.loads(config)
    except json.JSONDecodeError as e:
        err_console.print(f"[bold red]Invalid JSON config:[/bold red] {e}")
        raise typer.Exit(code=1)

    ctx, _ = make_context(database)
    request = CreateSourceRequest(
        name=name,
        source_type=source_type,
        config=config_dict,
        domain=domain,
        enabled=not disabled,
    )
    result = _register(ctx, request)
    output_result(result, as_json=json_out, title="Registered Source")


@app.command("get")
def get_source(
    source_id: str = typer.Argument(..., help="Source ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Get data source details."""
    from spine.ops.sources import get_source as _get

    ctx, _ = make_context(database)
    result = _get(ctx, source_id)
    output_result(result, as_json=json_out, title="Source Details")


@app.command("delete")
def delete_source(
    source_id: str = typer.Argument(..., help="Source ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    database: str | None = typer.Option(None, "--database", "-d"),
) -> None:
    """Delete a data source."""
    from spine.ops.sources import delete_source as _delete

    if not force:
        if not typer.confirm(f"Delete source {source_id}?"):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(code=0)

    ctx, _ = make_context(database)
    result = _delete(ctx, source_id)
    if result.success:
        console.print(f"[green]✓[/green] Deleted source {source_id}")
    else:
        err_console.print(f"[bold red]Error:[/bold red] {result.error.message if result.error else 'Unknown error'}")
        raise typer.Exit(code=1)


@app.command("enable")
def enable_source(
    source_id: str = typer.Argument(..., help="Source ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
) -> None:
    """Enable a data source."""
    from spine.ops.sources import enable_source as _enable

    ctx, _ = make_context(database)
    result = _enable(ctx, source_id)
    if result.success:
        console.print(f"[green]✓[/green] Enabled source {source_id}")
    else:
        err_console.print(f"[bold red]Error:[/bold red] {result.error.message if result.error else 'Unknown error'}")
        raise typer.Exit(code=1)


@app.command("disable")
def disable_source(
    source_id: str = typer.Argument(..., help="Source ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
) -> None:
    """Disable a data source."""
    from spine.ops.sources import disable_source as _disable

    ctx, _ = make_context(database)
    result = _disable(ctx, source_id)
    if result.success:
        console.print(f"[yellow]⏸[/yellow] Disabled source {source_id}")
    else:
        err_console.print(f"[bold red]Error:[/bold red] {result.error.message if result.error else 'Unknown error'}")
        raise typer.Exit(code=1)


# ------------------------------------------------------------------ #
# Fetch History Commands
# ------------------------------------------------------------------ #


@app.command("fetches")
def list_fetches(
    source_id: str | None = typer.Option(None, "--source-id"),
    source_name: str | None = typer.Option(None, "--source-name", "--name"),
    status: str | None = typer.Option(None, "--status"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List source fetch history."""
    from spine.ops.requests import ListSourceFetchesRequest
    from spine.ops.sources import list_source_fetches as _list

    ctx, _ = make_context(database)
    request = ListSourceFetchesRequest(
        source_id=source_id,
        source_name=source_name,
        status=status,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)
    output_paged(result, as_json=json_out, title="Source Fetches")


# ------------------------------------------------------------------ #
# Cache Commands
# ------------------------------------------------------------------ #


@app.command("cache")
def list_cache(
    source_id: str | None = typer.Option(None, "--source-id"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List source cache entries."""
    from spine.ops.sources import list_source_cache as _list

    ctx, _ = make_context(database)
    result = _list(ctx, source_id=source_id, limit=limit, offset=offset)
    output_paged(result, as_json=json_out, title="Source Cache")


@app.command("cache-invalidate")
def invalidate_cache(
    source_id: str = typer.Argument(..., help="Source ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    database: str | None = typer.Option(None, "--database", "-d"),
) -> None:
    """Invalidate all cache entries for a source."""
    from spine.ops.sources import invalidate_source_cache as _invalidate

    if not force:
        if not typer.confirm(f"Invalidate all cache for source {source_id}?"):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(code=0)

    ctx, _ = make_context(database)
    result = _invalidate(ctx, source_id)
    if result.success:
        deleted = result.data.get("deleted", 0) if result.data else 0
        console.print(f"[green]✓[/green] Invalidated {deleted} cache entries for {source_id}")
    else:
        err_console.print(f"[bold red]Error:[/bold red] {result.error.message if result.error else 'Unknown error'}")
        raise typer.Exit(code=1)


# ------------------------------------------------------------------ #
# Database Connection Commands
# ------------------------------------------------------------------ #


@app.command("connections")
def list_connections(
    dialect: str | None = typer.Option(None, "--dialect"),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List database connections."""
    from spine.ops.requests import ListDatabaseConnectionsRequest
    from spine.ops.sources import list_database_connections as _list

    ctx, _ = make_context(database)
    request = ListDatabaseConnectionsRequest(
        dialect=dialect,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)
    output_paged(result, as_json=json_out, title="Database Connections")


@app.command("connection-register")
def register_connection(
    name: str = typer.Argument(..., help="Unique connection name"),
    dialect: str = typer.Option("postgresql", "--dialect", help="Database dialect"),
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
    db_name: str = typer.Option(..., "--db", help="Database name"),
    username: str | None = typer.Option(None, "--user"),
    password_ref: str | None = typer.Option(None, "--password-ref", help="Reference to password secret"),
    disabled: bool = typer.Option(False, "--disabled", help="Create disabled"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Register a new database connection."""
    from spine.ops.requests import CreateDatabaseConnectionRequest
    from spine.ops.sources import register_database_connection as _register

    ctx, _ = make_context(database)
    request = CreateDatabaseConnectionRequest(
        name=name,
        dialect=dialect,
        host=host,
        port=port,
        database=db_name,
        username=username,
        password_ref=password_ref,
        enabled=not disabled,
    )
    result = _register(ctx, request)
    output_result(result, as_json=json_out, title="Registered Connection")


@app.command("connection-delete")
def delete_connection(
    connection_id: str = typer.Argument(..., help="Connection ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    database: str | None = typer.Option(None, "--database", "-d"),
) -> None:
    """Delete a database connection."""
    from spine.ops.sources import delete_database_connection as _delete

    if not force:
        if not typer.confirm(f"Delete connection {connection_id}?"):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(code=0)

    ctx, _ = make_context(database)
    result = _delete(ctx, connection_id)
    if result.success:
        console.print(f"[green]✓[/green] Deleted connection {connection_id}")
    else:
        err_console.print(f"[bold red]Error:[/bold red] {result.error.message if result.error else 'Unknown error'}")
        raise typer.Exit(code=1)


@app.command("connection-test")
def test_connection(
    connection_id: str = typer.Argument(..., help="Connection ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Test a database connection."""
    from spine.ops.sources import test_database_connection as _test

    ctx, _ = make_context(database)
    result = _test(ctx, connection_id)
    output_result(result, as_json=json_out, title="Connection Test")
