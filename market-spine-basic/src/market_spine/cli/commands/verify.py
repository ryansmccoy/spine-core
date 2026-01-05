"""Verification commands."""

from datetime import datetime
from typing import Annotated

import typer

from market_spine.app.services.data import DataSourceConfig
from market_spine.app.services.tier import TierNormalizer
from market_spine.db import get_connection, init_connection_provider

from ..console import console, get_tier_values
from ..ui import render_error_panel, render_info_panel

# Initialize connection provider
init_connection_provider()

# Service instances
_tier_normalizer = TierNormalizer()
_data_source = DataSourceConfig()

app = typer.Typer(no_args_is_help=True)


@app.command("table")
def verify_table(
    table_name: Annotated[str, typer.Argument(help="Table name to verify")],
) -> None:
    """Verify a table exists and show basic info."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        exists = cursor.fetchone() is not None

        if exists:
            console.print(f"[green]✓[/green] Table '{table_name}' exists")

            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]

            render_info_panel(title="Table Info", message=f"Table: {table_name}\nRows: {count:,}")
        else:
            console.print(f"[red]✗[/red] Table '{table_name}' not found")
            raise typer.Exit(1)

    except Exception as e:
        render_error_panel("Verification Error", str(e))
        raise typer.Exit(1)


@app.command("data")
def verify_data(
    tier: Annotated[
        str,
        typer.Option("--tier", help=f"Tier: {', '.join(get_tier_values())}"),
    ],
    week: Annotated[
        str,
        typer.Option("--week", help="Week ending date (YYYY-MM-DD)"),
    ],
) -> None:
    """Verify data quality for a week."""
    try:
        normalized_tier = _tier_normalizer.normalize(tier)
    except ValueError as e:
        render_error_panel("Invalid Tier", str(e))
        raise typer.Exit(1)

    try:
        # Validate date format
        datetime.strptime(week, "%Y-%m-%d")
    except ValueError:
        render_error_panel("Invalid Date", "Date must be in YYYY-MM-DD format")
        raise typer.Exit(1)

    try:
        conn = get_connection()
        cursor = conn.cursor()

        issues = []
        table = _data_source.normalized_data_table

        # Check if data exists
        cursor.execute(
            f"SELECT COUNT(*) FROM {table} WHERE week_ending = ? AND tier = ?",
            (week, normalized_tier),
        )
        count = cursor.fetchone()[0]

        if count == 0:
            issues.append(f"No data found for {week} ({normalized_tier})")
        else:
            # Check for nulls in required fields
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM {table}
                WHERE week_ending = ? AND tier = ?
                AND (symbol IS NULL OR total_shares IS NULL)
                """,
                (week, normalized_tier),
            )
            null_count = cursor.fetchone()[0]

            if null_count > 0:
                issues.append(f"{null_count} rows have null values in required fields")

        if not issues:
            console.print(
                f"[green]✓[/green] Data quality checks passed for {week} ({normalized_tier})"
            )
            console.print(f"[dim]{count} rows verified[/dim]")
        else:
            console.print(f"[yellow]⚠[/yellow] Found {len(issues)} issue(s):")
            for issue in issues:
                console.print(f"  • {issue}")
            raise typer.Exit(1)

    except Exception as e:
        render_error_panel("Verification Error", str(e))
        raise typer.Exit(1)
