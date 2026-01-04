"""Query commands for data inspection."""

from typing import Optional

import typer
from rich.table import Table
from typing_extensions import Annotated

from market_spine.app.commands.queries import (
    QuerySymbolsCommand,
    QuerySymbolsRequest,
    QueryWeeksCommand,
    QueryWeeksRequest,
)

from ..console import console, get_tier_values
from ..ui import render_error_panel

app = typer.Typer(no_args_is_help=True)

# Get tier values once at module load
_tier_values = get_tier_values()


@app.command("weeks")
def query_weeks(
    tier: Annotated[
        str,
        typer.Option("--tier", help=f"Tier: OTC, NMS_TIER_1, NMS_TIER_2"),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Max weeks to show"),
    ] = 10,
) -> None:
    """Show available weeks for a tier."""
    # Build request and execute command
    command = QueryWeeksCommand()
    result = command.execute(QueryWeeksRequest(tier=tier, limit=limit))

    # Handle errors
    if not result.success:
        render_error_panel(result.error.code.value, result.error.message)
        raise typer.Exit(1)

    # Handle empty results
    if not result.weeks:
        console.print(f"[yellow]No data found for tier {result.tier}[/yellow]")
        return

    # Render results
    table = Table(title=f"Available Weeks - {result.tier}")
    table.add_column("Week Ending", style="cyan")
    table.add_column("Symbol Count", justify="right")

    for week in result.weeks:
        table.add_row(week.week_ending, str(week.symbol_count))

    console.print(table)
    console.print(f"\n[dim]Showing {len(result.weeks)} week(s)[/dim]")


@app.command("symbols")
def query_symbols(
    week: Annotated[
        str,
        typer.Option("--week", help="Week ending date (YYYY-MM-DD)"),
    ],
    tier: Annotated[
        str,
        typer.Option("--tier", help=f"Tier: OTC, NMS_TIER_1, NMS_TIER_2"),
    ],
    top: Annotated[
        int,
        typer.Option("--top", "-n", help="Number of symbols to show"),
    ] = 10,
) -> None:
    """Show top symbols by volume for a week."""
    # Build request and execute command
    command = QuerySymbolsCommand()
    result = command.execute(QuerySymbolsRequest(tier=tier, week=week, top=top))

    # Handle errors
    if not result.success:
        render_error_panel(result.error.code.value, result.error.message)
        raise typer.Exit(1)

    # Handle empty results
    if not result.symbols:
        console.print(f"[yellow]No symbols found for {result.week} in {result.tier}[/yellow]")
        return

    # Render results
    table = Table(title=f"Top {top} Symbols - {result.tier} - {result.week}")
    table.add_column("Symbol", style="cyan")
    table.add_column("Volume", justify="right")
    table.add_column("Avg Price", justify="right")

    for sym in result.symbols:
        volume_str = f"{sym.volume:,.0f}" if sym.volume else "0"
        price_str = f"${sym.avg_price:.2f}" if sym.avg_price else "$0.00"
        table.add_row(sym.symbol, volume_str, price_str)

    console.print(table)
