"""Database management commands."""

from typing import Annotated

import typer

from market_spine.db import (
    init_db as db_init,
)
from market_spine.db import (
    reset_db as db_reset,
)

from ..console import console
from ..ui import render_error_panel, render_info_panel

app = typer.Typer(no_args_is_help=True)


@app.command("init")
def init_db_command(
    force: Annotated[
        bool,
        typer.Option("--force", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Initialize database schema."""
    if not force:
        confirm = typer.confirm("Initialize database schema?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

    try:
        db_init()
        render_info_panel(
            title="Database Initialized", message="Schema tables created successfully"
        )
    except Exception as e:
        render_error_panel("Initialization Error", str(e))
        raise typer.Exit(1)


@app.command("reset")
def reset_db_command(
    force: Annotated[
        bool,
        typer.Option("--force", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Reset database (DROP all tables and reinitialize)."""
    if not force:
        console.print("[bold red]WARNING:[/bold red] This will delete ALL data!")
        confirm = typer.confirm("Are you sure you want to reset the database?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

    try:
        db_reset()
        render_info_panel(title="Database Reset", message="All tables dropped and recreated")
    except Exception as e:
        render_error_panel("Reset Error", str(e))
        raise typer.Exit(1)
