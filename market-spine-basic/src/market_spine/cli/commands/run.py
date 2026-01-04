"""Pipeline execution commands."""

import time
from typing import Optional

import typer
from rich.panel import Panel
from typing_extensions import Annotated

from market_spine.app.commands.executions import RunPipelineCommand, RunPipelineRequest
from market_spine.app.commands.pipelines import DescribePipelineCommand, DescribePipelineRequest
from market_spine.app.models import ErrorCode
from market_spine.app.services.ingest import IngestResolver
from market_spine.app.services.tier import TierNormalizer

from ..console import console, get_tier_values
from ..params import ParamParser
from ..ui import render_dry_run_panel, render_error_panel, render_summary_panel

# Valid lane values (matching spine.framework.dispatcher.Lane)
LANE_VALUES = ["normal", "backfill", "slow"]

# Create sub-app for run commands
app = typer.Typer(no_args_is_help=True)


@app.command("run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run_pipeline(
    ctx: typer.Context,
    pipeline: Annotated[str, typer.Argument(help="Pipeline name (e.g., finra.otc_transparency.normalize_week)")],
    param: Annotated[
        Optional[list[str]],
        typer.Option("-p", "--param", help="Parameter as key=value (repeatable)"),
    ] = None,
    week_ending: Annotated[
        Optional[str],
        typer.Option("--week-ending", "--week", help="Week ending date (YYYY-MM-DD)"),
    ] = None,
    tier: Annotated[
        Optional[str],
        typer.Option("--tier", help=f"Tier: {', '.join(get_tier_values())}"),
    ] = None,
    file_path: Annotated[
        Optional[str],
        typer.Option("--file", help="File path for ingest"),
    ] = None,
    lane: Annotated[
        str,
        typer.Option("--lane", help="Execution lane: normal, backfill, slow"),
    ] = "normal",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would execute without running"),
    ] = False,
    help_params: Annotated[
        bool,
        typer.Option("--help-params", help="Show pipeline parameters"),
    ] = False,
    explain_source: Annotated[
        bool,
        typer.Option("--explain-source", help="Show how ingest source is resolved"),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress logs, show only summary"),
    ] = False,
) -> None:
    """
    Run a pipeline with parameters.
    
    Parameters can be provided in three ways:
    1. Friendly options: --week-ending 2025-12-05 --tier OTC
    2. Key=value args: week_ending=2025-12-05 tier=OTC
    3. -p flags: -p week_ending=2025-12-05 -p tier=OTC
    """
    # Show parameter help if requested (CLI-only feature)
    if help_params:
        show_pipeline_params(pipeline)
        return

    # Parse parameters from all sources (CLI-specific parsing)
    param_flags = param or []
    extra_args = tuple(ctx.args) if ctx.args else ()
    tier_values = get_tier_values()

    try:
        params = ParamParser.merge_params(
            param_flags=param_flags,
            extra_args=extra_args,
            week_ending=week_ending,
            tier=tier,
            file_path=file_path,
        )
    except ValueError as e:
        # Enhanced tier error messages (CLI-only formatting)
        error_msg = str(e)
        details = []
        
        if "tier" in error_msg.lower():
            details.append(f"Valid tier values: {', '.join(tier_values)}")
            details.append("")
            details.append("Tier aliases also accepted:")
            details.append("  Tier1, tier1 → NMS_TIER_1")
            details.append("  Tier2, tier2 → NMS_TIER_2")
            details.append("  OTC, otc → OTC")
        
        render_error_panel("Parameter Error", error_msg, details=details)
        raise typer.Exit(1)
    except Exception as e:
        render_error_panel("Parameter Error", str(e))
        raise typer.Exit(1)

    # Show ingest source resolution if requested (CLI-only feature)
    is_ingest_pipeline = "ingest" in pipeline
    if explain_source or (is_ingest_pipeline and not file_path):
        show_ingest_resolution(pipeline, params, is_ingest_pipeline)

    # Build request and execute command
    command = RunPipelineCommand()
    result = command.execute(
        RunPipelineRequest(
            pipeline=pipeline,
            params=params,
            lane=lane.lower(),
            dry_run=dry_run,
            trigger_source="cli",
        )
    )

    # Handle dry run result
    if dry_run:
        render_dry_run_panel(pipeline, params, is_ingest=is_ingest_pipeline)
        return

    # Handle errors
    if not result.success:
        error = result.error
        
        if error.code == ErrorCode.PIPELINE_NOT_FOUND:
            render_error_panel(
                "Unknown Pipeline",
                error.message,
                details=["Use 'spine pipelines list' to see available pipelines."],
            )
        elif error.code == ErrorCode.INVALID_PARAMS:
            details = []
            if error.details.get("missing"):
                details.append(f"[red]Missing required:[/red] {', '.join(error.details['missing'])}")
            if error.details.get("invalid"):
                details.append(f"[yellow]Invalid:[/yellow] {', '.join(error.details['invalid'])}")
            details.append("")
            details.append(f"Run 'spine pipelines describe {pipeline}' for full parameter details")
            details.append(f"Or use 'spine run {pipeline} --help-params' for quick reference")
            render_error_panel("Parameter Validation Failed", error.message, details=details)
        elif error.code == ErrorCode.INVALID_TIER:
            details = [
                f"Valid tier values: {', '.join(tier_values)}",
                "",
                "Tier aliases also accepted:",
                "  Tier1, tier1 → NMS_TIER_1",
                "  Tier2, tier2 → NMS_TIER_2",
                "  OTC, otc → OTC",
            ]
            render_error_panel("Invalid Tier", error.message, details=details)
        else:
            render_error_panel(error.code.value, error.message)
        
        raise typer.Exit(1)

    # Render success summary
    metrics_dict = None
    if result.metrics:
        metrics_dict = {
            "rows_processed": result.metrics.rows_processed,
            **result.metrics.extra,
        }
        if result.metrics.capture_id:
            metrics_dict["capture_id"] = result.metrics.capture_id

    render_summary_panel(
        status="completed",
        duration=result.duration_seconds or 0,
        metrics=metrics_dict,
        capture_id=result.metrics.capture_id if result.metrics else None,
    )


def show_ingest_resolution(pipeline_name: str, params: dict, is_ingest: bool) -> None:
    """Show how ingest source will be resolved."""
    if not is_ingest:
        console.print("[dim]This pipeline does not perform ingest operations.[/dim]\n")
        return

    lines = []
    lines.append("[bold cyan]Ingest Source Resolution:[/bold cyan]")
    lines.append("")

    if "file_path" in params and params["file_path"]:
        # Explicit file mode
        lines.append("  Mode: [green]Explicit File[/green]")
        lines.append(f"  File: [cyan]{params['file_path']}[/cyan]")
        lines.append("")
        lines.append("  [dim]Using user-specified file path.[/dim]")
    else:
        # Derived mode - use IngestResolver for preview
        lines.append("  Mode: [yellow]Derived Local Resolution[/yellow]")
        lines.append("")
        
        week = params.get("week_ending", "<unknown>")
        tier = params.get("tier", "<unknown>")
        
        if week != "<unknown>" and tier != "<unknown>":
            # Use IngestResolver for consistent derivation
            resolver = IngestResolver()
            normalizer = TierNormalizer()
            
            try:
                canonical_tier = normalizer.normalize(tier)
                derived_path = resolver.derive_file_path_preview(canonical_tier, week)
                
                lines.append(f"  Week ending: [cyan]{week}[/cyan]")
                lines.append(f"  Tier: [cyan]{canonical_tier}[/cyan]")
                lines.append("")
                lines.append(f"  Resolved path: [cyan]{derived_path}[/cyan]")
                lines.append("")
                lines.append("  [dim]Path derived from week_ending and tier parameters.[/dim]")
                lines.append("  [dim]Use --file to override with explicit path.[/dim]")
            except ValueError:
                lines.append(f"  [yellow]Cannot derive path: invalid tier '{tier}'[/yellow]")
        else:
            lines.append("  [yellow]Cannot derive path: missing week_ending or tier[/yellow]")

    panel = Panel("\n".join(lines), border_style="cyan", title="Source Resolution")
    console.print(panel)
    console.print()


def show_pipeline_params(pipeline_name: str) -> None:
    """Show parameters for a pipeline."""
    # Use DescribePipelineCommand
    command = DescribePipelineCommand()
    result = command.execute(DescribePipelineRequest(name=pipeline_name))

    if not result.success:
        render_error_panel(
            "Unknown Pipeline",
            f"Pipeline '{pipeline_name}' not found.",
        )
        raise typer.Exit(1)

    detail = result.pipeline
    
    console.print(f"\n[bold cyan]Pipeline:[/bold cyan] {detail.name}")
    console.print(f"[bold cyan]Description:[/bold cyan] {detail.description}\n")

    has_params = detail.required_params or detail.optional_params
    
    if has_params:
        console.print("[bold]Parameters:[/bold]")
        
        # Show required params first
        for param in detail.required_params:
            console.print(f"  • {param.name} [red](required)[/red]")
            if param.description:
                console.print(f"    {param.description}")
                
        # Then optional params
        for param in detail.optional_params:
            console.print(f"  • {param.name} [dim](optional)[/dim]")
            if param.description:
                console.print(f"    {param.description}")
            if param.default is not None:
                console.print(f"    [dim]Default: {param.default}[/dim]")
    else:
        console.print("[dim]No parameters defined[/dim]")
