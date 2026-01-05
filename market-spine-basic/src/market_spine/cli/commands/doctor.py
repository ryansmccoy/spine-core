"""Health check command."""

import typer
from rich.table import Table

from market_spine.app.services.data import DataSourceConfig
from market_spine.db import get_connection

from ..console import console

app = typer.Typer(no_args_is_help=False)

# Service instance
_data_source = DataSourceConfig()


@app.command("doctor")
def doctor() -> None:
    """Run health checks on the system."""
    checks = []

    # Check database connection
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            db_ok = result[0] == 1
    except Exception as e:
        db_ok = False
        db_error = str(e)

    checks.append(("Database Connection", db_ok, db_error if not db_ok else None))

    # Check required tables (from DataSourceConfig)
    required_tables = [
        _data_source.raw_data_table,
        _data_source.normalized_data_table,
        _data_source.aggregated_data_table,
    ]

    for table in required_tables:
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                )
                exists = cursor.fetchone() is not None
            checks.append((f"Table: {table}", exists, None))
        except Exception as e:
            checks.append((f"Table: {table}", False, str(e)))

    # Display results
    table = Table(title="Health Check Results")
    table.add_column("Check", style="cyan")
    table.add_column("Status", justify="center")

    all_ok = True
    for check_name, ok, error in checks:
        status = "[green]✓[/green]" if ok else "[red]✗[/red]"
        table.add_row(check_name, status)
        if not ok:
            all_ok = False
            if error:
                console.print(f"  [red]Error: {error}[/red]")

    console.print(table)

    if all_ok:
        console.print("\n[green]All checks passed[/green]")
    else:
        console.print("\n[yellow]Some checks failed[/yellow]")
        raise typer.Exit(1)
