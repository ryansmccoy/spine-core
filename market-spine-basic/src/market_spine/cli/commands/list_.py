"""Pipeline discovery and inspection commands."""

from typing import Optional

import typer
from rich.panel import Panel
from typing_extensions import Annotated

from market_spine.app.commands.pipelines import (
    DescribePipelineCommand,
    DescribePipelineRequest,
    ListPipelinesCommand,
    ListPipelinesRequest,
)

from ..console import console
from ..ui import create_pipeline_table, render_error_panel

app = typer.Typer(no_args_is_help=False, help="Pipeline discovery and inspection")


@app.command("list")
def list_pipelines_cmd(
    prefix: Annotated[
        Optional[str],
        typer.Option("--prefix", help="Filter by pipeline prefix"),
    ] = None,
) -> None:
    """List all available pipelines."""
    # Build request and execute command
    command = ListPipelinesCommand()
    result = command.execute(ListPipelinesRequest(prefix=prefix))

    # Handle errors
    if not result.success:
        render_error_panel(result.error.code.value, result.error.message)
        raise typer.Exit(1)

    # Handle empty results
    if not result.pipelines:
        if prefix:
            console.print(f"[yellow]No pipelines found matching prefix: {prefix}[/yellow]")
            console.print(f"\n[dim]Hint: Use 'spine pipelines list' to see all available pipelines[/dim]")
        else:
            console.print("[yellow]No pipelines registered[/yellow]")
        return

    # Display table - use data from command result
    pipeline_data = [(p.name, p.description) for p in result.pipelines]
    table = create_pipeline_table(pipeline_data)
    console.print(table)
    console.print(f"\n[dim]Found {len(result.pipelines)} pipeline(s)[/dim]")


@app.command("describe")
def describe_pipeline(
    pipeline: Annotated[str, typer.Argument(help="Pipeline name to describe")],
) -> None:
    """Show detailed information about a pipeline including parameters and examples."""
    # Build request and execute command
    command = DescribePipelineCommand()
    result = command.execute(DescribePipelineRequest(name=pipeline))

    # Handle errors
    if not result.success:
        if result.error.code.value == "PIPELINE_NOT_FOUND":
            render_error_panel(
                "Unknown Pipeline",
                f"Pipeline '{pipeline}' not found.",
                details=["Use 'spine pipelines list' to see available pipelines."],
            )
        else:
            render_error_panel(result.error.code.value, result.error.message)
        raise typer.Exit(1)

    # Render pipeline details
    detail = result.pipeline

    # Header
    console.print(f"\n[bold cyan]Pipeline:[/bold cyan] {detail.name}")
    console.print(f"[bold cyan]Description:[/bold cyan] {detail.description}\n")

    # Parameters section
    has_params = detail.required_params or detail.optional_params

    if has_params:
        console.print("[bold]Parameters:[/bold]\n")

        # Required parameters
        if detail.required_params:
            console.print("  [bold red]Required:[/bold red]")
            for param in detail.required_params:
                console.print(f"    • [cyan]{param.name}[/cyan]")
                if param.description:
                    console.print(f"      {param.description}")
                if param.name == "tier" and param.choices:
                    console.print(f"      Valid values: {', '.join(param.choices)}")
            console.print()

        # Optional parameters
        if detail.optional_params:
            console.print("  [bold green]Optional:[/bold green]")
            for param in detail.optional_params:
                default_str = f" (default: {param.default})" if param.default is not None else ""
                console.print(f"    • [cyan]{param.name}[/cyan]{default_str}")
                if param.description:
                    console.print(f"      {param.description}")
            console.print()
    else:
        console.print("[dim]No parameters defined[/dim]\n")

    # Ingest resolution for ingest pipelines
    if detail.is_ingest:
        console.print("[bold]Ingest Source Resolution:[/bold]\n")
        console.print("  When [cyan]--file[/cyan] is provided:")
        console.print("    • Uses the specified file path directly\n")
        console.print("  When [cyan]--file[/cyan] is omitted:")
        console.print("    • Derives file path from week_ending and tier")
        console.print("    • Pattern: [dim]data/finra/finra_otc_weekly_{tier}_{date}.csv[/dim]")
        console.print("    • Use [cyan]--dry-run[/cyan] to see resolved path before execution\n")

    # Examples
    console.print("[bold]Example Usage:[/bold]\n")

    # Generate contextual examples based on pipeline type
    if detail.is_ingest:
        console.print("  # With explicit file:")
        console.print(f"  spine run {pipeline} \\")
        console.print("    --file data/finra/weekly_otc.csv \\")
        console.print("    --week-ending 2025-12-19 \\")
        console.print("    --tier OTC\n")
        console.print("  # With derived file path:")
        console.print(f"  spine run {pipeline} \\")
        console.print("    --week-ending 2025-12-19 \\")
        console.print("    --tier OTC\n")
    elif "normalize" in pipeline:
        console.print(f"  spine run {pipeline} \\")
        console.print("    --week-ending 2025-12-19 \\")
        console.print("    --tier NMS_TIER_1\n")
    elif "aggregate" in pipeline:
        console.print(f"  spine run {pipeline} \\")
        console.print("    --week-ending 2025-12-19 \\")
        console.print("    --tier NMS_TIER_1\n")
    elif "backfill" in pipeline:
        console.print(f"  spine run {pipeline} \\")
        console.print("    start_date=2025-11-01 \\")
        console.print("    end_date=2025-12-31 \\")
        console.print("    tier=OTC\n")
    else:
        console.print(f"  spine run {pipeline} --help-params\n")

    # Helpful hints
    console.print("[bold]Helpful Commands:[/bold]\n")
    console.print(f"  spine run {pipeline} --dry-run     # Preview execution")
    console.print(f"  spine run {pipeline} --help        # Show all CLI options")
