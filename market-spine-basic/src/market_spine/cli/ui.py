"""Rich UI components for panels, progress, and formatting."""

from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .console import console


def render_summary_panel(
    status: str,
    duration: float,
    metrics: dict[str, Any] | None = None,
    capture_id: str | None = None,
) -> None:
    """Render execution summary panel."""
    lines = []

    # Status with icon
    status_icon = "✓" if status.lower() == "completed" else "✗"
    lines.append(f"Status: {status_icon} {status.title()}")
    lines.append(f"Duration: {duration:.2f}s")

    if capture_id:
        lines.append(f"Capture ID: {capture_id}")

    if metrics:
        lines.append("")
        lines.append("Metrics:")
        for key, value in metrics.items():
            if key not in ["capture_id", "captured_at"]:
                # Format key nicely
                display_key = key.replace("_", " ").title()
                lines.append(f"  • {display_key}: {value}")

    panel = Panel(
        "\n".join(lines),
        title="Summary",
        border_style="green" if status.lower() == "completed" else "red",
    )
    console.print(panel)


def render_error_panel(title: str, message: str, details: list[str] | None = None) -> None:
    """Render error panel."""
    lines = [message]

    if details:
        lines.append("")
        for detail in details:
            lines.append(f"  • {detail}")

    panel = Panel("\n".join(lines), title=title, border_style="red")
    console.print(panel)


def render_info_panel(title: str, message: str = None, content: dict[str, Any] = None) -> None:
    """Render informational panel."""
    lines = []
    
    if message:
        lines.append(message)
    
    if content:
        for key, value in content.items():
            display_key = key.replace("_", " ").title()
            lines.append(f"{display_key}: {value}")

    panel = Panel("\n".join(lines), title=title, border_style="cyan")
    console.print(panel)


def render_dry_run_panel(pipeline: str, params: dict[str, Any], is_ingest: bool = False) -> None:
    """Render dry-run panel showing what would execute."""
    lines = [f"Pipeline: {pipeline}", ""]

    if params:
        lines.append("Resolved Parameters:")
        for key, value in params.items():
            lines.append(f"  • {key}: {value}")
    else:
        lines.append("No parameters")

    # Add ingest resolution hint if applicable
    if is_ingest and "file_path" not in params:
        lines.append("")
        lines.append("[dim]Note: Ingest source will be derived from parameters.[/dim]")
        lines.append("[dim]Use --explain-source to see file resolution logic.[/dim]")

    lines.append("")
    lines.append("Would execute with these parameters.")
    lines.append("(Use without --dry-run to actually run)")

    panel = Panel("\n".join(lines), title="Dry Run", border_style="yellow")
    console.print(panel)


def create_pipeline_table(pipelines: list[tuple[str, str]]) -> Table:
    """
    Create a table of pipelines.
    
    Args:
        pipelines: List of (name, description) tuples
    
    Returns:
        Rich Table ready for display
    """
    table = Table(title="Available Pipelines")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")

    for name, description in pipelines:
        table.add_row(name, description or "[dim]No description[/dim]")

    return table


def render_phase(phase: int, total: int, description: str, status: str = "running") -> None:
    """Render a phase status line."""
    if status == "running":
        icon = "⠹"
        style = "cyan"
    elif status == "complete":
        icon = "✓"
        style = "green"
    else:
        icon = "✗"
        style = "red"

    text = Text(f"{icon} Phase {phase}/{total}: {description}", style=style)
    console.print(text)
