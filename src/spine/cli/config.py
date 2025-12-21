"""
CLI: ``spine-core config`` — configuration inspection and management.
"""

from __future__ import annotations

import typer

from spine.cli.utils import console

app = typer.Typer(no_args_is_help=True)


@app.command("show")
def show_config(
    all_settings: bool = typer.Option(False, "--all", "-a", help="Show all settings"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json, env"),
) -> None:
    """Show current configuration."""
    from spine.core.config import get_settings

    settings = get_settings()

    if format == "json":
        console.print_json(settings.model_dump_json())
        return

    if format == "env":
        for key, value in sorted(settings.model_dump().items()):
            if not key.startswith("_"):
                console.print(f"SPINE_{key.upper()}={value}")
        return

    # Table format
    from rich.table import Table

    console.print(f"[bold]Tier:[/bold] {settings.infer_tier()}")

    project_root = getattr(settings, "_project_root", None)
    if project_root:
        console.print(f"[bold]Project Root:[/bold] {project_root}")

    env_files = getattr(settings, "_env_files_loaded", [])
    if env_files:
        console.print("[bold]Env Files Loaded:[/bold]")
        for f in env_files:
            console.print(f"  • {f}")

    active_profile = getattr(settings, "_active_profile", None)
    if active_profile:
        console.print(f"[bold]Active Profile:[/bold] {active_profile}")

    console.print("\n[bold]Components:[/bold]")
    table = Table()
    table.add_column("Component")
    table.add_column("Value")
    table.add_row("Database", settings.database_backend.value)
    table.add_row("Scheduler", settings.scheduler_backend.value)
    table.add_row("Cache", settings.cache_backend.value)
    table.add_row("Worker", settings.worker_backend.value)
    table.add_row("Metrics", settings.metrics_backend.value)
    table.add_row("Tracing", settings.tracing_backend.value)
    console.print(table)

    if all_settings:
        console.print("\n[bold]All Settings:[/bold]")
        for key, value in sorted(settings.model_dump().items()):
            if not key.startswith("_"):
                console.print(f"  {key}: {value}")


@app.command("validate")
def validate_config() -> None:
    """Validate configuration and show warnings."""
    from spine.core.config import get_settings

    try:
        settings = get_settings(_force_reload=True)
    except ValueError as e:
        console.print(f"[red]Configuration Error:[/red] {e}")
        raise typer.Exit(1) from e

    console.print(f"[bold]Tier:[/bold] {settings.infer_tier()}")

    if settings.component_warnings:
        console.print("\n[bold]Warnings:[/bold]")
        for w in settings.component_warnings:
            color = {"info": "blue", "warning": "yellow"}.get(w.severity, "red")
            console.print(f"  [{color}]{w.severity.upper()}:[/{color}] {w.message}")
            console.print(f"         → {w.suggestion}")
    else:
        console.print("[green]✓ No compatibility warnings[/green]")


@app.command("init")
def init_config(
    tier: str = typer.Option("minimal", "--tier", "-t", help="Tier: minimal, standard, full"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files"),
) -> None:
    """Initialize configuration files in project root."""

    from spine.core.config import find_project_root

    root = find_project_root()
    source = root / f".env.{tier}"
    target = root / ".env.local"

    if target.exists() and not force:
        console.print(f"[yellow]Warning:[/yellow] {target} already exists. Use --force to overwrite.")
        raise typer.Exit(1)

    if source.exists():
        target.write_text(source.read_text())
        console.print(f"[green]✓[/green] Created {target} from {tier} tier")
    else:
        console.print(f"[red]Error:[/red] {source} not found")
        raise typer.Exit(1)

    console.print(f"\nEdit {target} to customize settings.")
    console.print("Run `spine-core config validate` to check configuration.")


@app.command("tier")
def show_tier() -> None:
    """Show detected tier."""
    from spine.core.config import get_settings

    settings = get_settings()
    console.print(settings.infer_tier())


@app.command("env")
def show_env_files() -> None:
    """Show which .env files would be loaded."""
    from spine.core.config import discover_env_files, find_project_root

    root = find_project_root()
    files = discover_env_files(root)

    console.print(f"[bold]Project Root:[/bold] {root}")
    console.print("[bold]Files (in load order):[/bold]")
    for f in files:
        console.print(f"  ✓ {f}")
