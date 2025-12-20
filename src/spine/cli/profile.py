"""
CLI: ``spine-core profile`` — TOML profile management.
"""

from __future__ import annotations

import typer

from spine.cli.utils import console

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_profiles(
    scope: str = typer.Option("all", "--scope", "-s", help="Scope: all, user, project"),
) -> None:
    """List available profiles."""
    from rich.table import Table

    from spine.core.config.profiles import get_profile_manager

    manager = get_profile_manager()
    profiles = manager.list_profiles(scope=scope)
    active = manager.get_active_profile()

    if not profiles:
        console.print("[dim]No profiles found.[/dim]")
        console.print("Create one with: spine-core profile create <name>")
        return

    table = Table(title="Available Profiles")
    table.add_column("Name")
    table.add_column("Scope")
    table.add_column("Inherits")
    table.add_column("Description")
    table.add_column("Active", justify="center")

    for p in profiles:
        is_active = "✓" if p.name == active else ""
        scope_label = "user" if "/.spine/" not in str(p.path) else "project"
        # More reliable: check against known dirs
        proj_dir = str(manager.project_profile_dir)
        scope_label = "project" if str(p.path).startswith(proj_dir) else "user"
        table.add_row(
            p.name,
            scope_label,
            p.inherits or "-",
            p.description or "-",
            f"[green]{is_active}[/green]" if is_active else "",
        )

    console.print(table)


@app.command("show")
def show_profile(
    name: str = typer.Argument(..., help="Profile name"),
    format: str = typer.Option("table", "--format", "-f", help="Output: table, json, env"),
) -> None:
    """Show a profile's settings."""
    import json

    from spine.core.config.profiles import get_profile_manager

    manager = get_profile_manager()
    profile = manager.get_profile(name)

    if profile is None:
        console.print(f"[red]Profile not found:[/red] {name}")
        raise typer.Exit(1)

    if format == "json":
        console.print_json(
            json.dumps(
                {
                    "name": profile.name,
                    "path": str(profile.path),
                    "inherits": profile.inherits,
                    "description": profile.description,
                    "settings": profile.settings,
                }
            )
        )
        return

    if format == "env":
        resolved = manager.resolve_profile(name)
        for key, value in sorted(resolved.items()):
            console.print(f"{key}={value}")
        return

    # Table format
    console.print(f"[bold]Profile:[/bold] {profile.name}")
    console.print(f"[bold]Path:[/bold] {profile.path}")
    if profile.inherits:
        console.print(f"[bold]Inherits:[/bold] {profile.inherits}")
    if profile.description:
        console.print(f"[bold]Description:[/bold] {profile.description}")

    console.print("\n[bold]Settings:[/bold]")
    for key, value in profile.settings.items():
        if isinstance(value, dict):
            console.print(f"  [{key}]")
            for subkey, subvalue in value.items():
                console.print(f"    {subkey} = {subvalue}")
        else:
            console.print(f"  {key} = {value}")

    # Show resolved if inheriting
    if profile.inherits:
        console.print("\n[bold]Resolved (with inheritance):[/bold]")
        resolved = manager.resolve_profile(name)
        for key, value in sorted(resolved.items()):
            console.print(f"  {key} = {value}")


@app.command("create")
def create_profile(
    name: str = typer.Argument(..., help="Profile name"),
    inherit: str | None = typer.Option(None, "--inherit", "-i", help="Inherit from profile"),
    scope: str = typer.Option("project", "--scope", "-s", help="Scope: user, project"),
    description: str = typer.Option("", "--description", "-d", help="Profile description"),
) -> None:
    """Create a new profile."""
    from spine.core.config.profiles import get_profile_manager

    manager = get_profile_manager()

    if manager.get_profile(name):
        console.print(f"[red]Profile already exists:[/red] {name}")
        raise typer.Exit(1)

    if inherit and not manager.get_profile(inherit):
        console.print(f"[red]Parent profile not found:[/red] {inherit}")
        raise typer.Exit(1)

    try:
        profile = manager.create_profile(
            name,
            scope=scope,
            inherits=inherit,
            description=description,
        )
        console.print(f"[green]✓[/green] Created profile: {profile.path}")
        console.print("\nEdit the profile to add settings:")
        console.print(f"  {profile.path}")
    except FileExistsError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("use")
def use_profile(
    name: str = typer.Argument(..., help="Profile name"),
    scope: str = typer.Option("project", "--scope", "-s", help="Scope: user, project"),
) -> None:
    """Set the default profile."""
    from spine.core.config.profiles import get_profile_manager

    manager = get_profile_manager()

    if not manager.get_profile(name):
        console.print(f"[red]Profile not found:[/red] {name}")
        raise typer.Exit(1)

    manager.set_default_profile(name, scope=scope)
    console.print(f"[green]✓[/green] Set default profile ({scope}): {name}")


@app.command("delete")
def delete_profile(
    name: str = typer.Argument(..., help="Profile name"),
    scope: str = typer.Option("project", "--scope", "-s", help="Scope: user, project"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a profile."""
    from spine.core.config.profiles import get_profile_manager

    manager = get_profile_manager()
    profile = manager.get_profile(name)

    if not profile:
        console.print(f"[red]Profile not found:[/red] {name}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Delete profile {name}?")
        if not confirm:
            raise typer.Abort()

    if manager.delete_profile(name, scope=scope):
        console.print(f"[green]✓[/green] Deleted profile: {name}")
    else:
        console.print(f"[yellow]Profile not found in {scope} scope[/yellow]")


@app.command("active")
def active_profile() -> None:
    """Show the currently active profile."""
    from spine.core.config.profiles import get_profile_manager

    manager = get_profile_manager()
    active = manager.get_active_profile()

    if active:
        console.print(active)
    else:
        console.print("[dim]No active profile[/dim]")


@app.command("export")
def export_profile(
    name: str = typer.Argument(..., help="Profile name"),
) -> None:
    """Export profile as .env format (stdout)."""
    from spine.core.config.profiles import get_profile_manager

    manager = get_profile_manager()

    if not manager.get_profile(name):
        console.print("[red]Profile not found:[/red] " + name, err=True)
        raise typer.Exit(1)

    resolved = manager.resolve_profile(name)
    for key, value in sorted(resolved.items()):
        print(f"{key}={value}")
