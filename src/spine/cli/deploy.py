"""
CLI: ``spine-core deploy`` — deployment and testbed commands.

Provides sub-commands for:
- Running the multi-backend testbed
- Deploying Spine ecosystem services
- Managing container lifecycles
- Collecting deployment artifacts

Usage::

    spine-core deploy testbed                      # SQLite-only quick run
    spine-core deploy testbed --backend postgresql  # Single backend
    spine-core deploy testbed --backend all         # All backends

    spine-core deploy up                            # Launch services
    spine-core deploy down                          # Stop services
    spine-core deploy status                        # Check service health
    spine-core deploy logs                          # Collect container logs

    spine-core deploy backends                      # List available backends
    spine-core deploy services                      # List available services
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(no_args_is_help=True)
console = Console()
err_console = Console(stderr=True)


# ── Testbed ──────────────────────────────────────────────────────────────


@app.command()
def testbed(
    backend: list[str] = typer.Option(
        ["sqlite"], "--backend", "-b",
        help="Backend(s) to test. Repeatable. Use 'all' for all.",
    ),
    parallel: bool = typer.Option(False, "--parallel", "-p", help="Run backends in parallel."),
    keep: bool = typer.Option(False, "--keep", help="Keep containers after run."),
    output_dir: str | None = typer.Option(None, "--output", "-o", help="Output directory."),
    output_format: str = typer.Option("all", "--format", "-f", help="Output format: json, html, all."),
    test_filter: str | None = typer.Option(None, "--test-filter", "-k", help="Pytest -k filter expression."),
    no_schema: bool = typer.Option(False, "--no-schema", help="Skip schema verification."),
    no_tests: bool = typer.Option(False, "--no-tests", help="Skip test suite."),
    no_examples: bool = typer.Option(False, "--no-examples", help="Skip example runner."),
    timeout: int = typer.Option(600, "--timeout", "-t", help="Per-backend timeout in seconds."),
    json_out: bool = typer.Option(False, "--json", help="Output results as JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
) -> None:
    """Run the multi-backend testbed.

    Starts database containers, loads schemas, executes tests,
    and collects results across one or more database backends.
    """
    from spine.deploy.config import TestbedConfig
    from spine.deploy.workflow import TestbedRunner

    config = TestbedConfig(
        backends=backend,
        parallel=parallel,
        keep_containers=keep,
        output_format=output_format,
        test_filter=test_filter,
        run_schema=not no_schema,
        run_tests=not no_tests,
        run_examples=not no_examples,
        backend_timeout_seconds=timeout,
    )
    if output_dir:
        config.output_dir = Path(output_dir)

    console.print(f"[bold]spine-core testbed[/] — run_id: {config.run_id}")
    console.print(f"  backends: {', '.join(config.backends)}")
    console.print(f"  parallel: {config.parallel}")

    runner = TestbedRunner(config)
    result = runner.run()

    if json_out:
        typer.echo(result.model_dump_json(indent=2))
    else:
        _print_testbed_result(result)

    if result.overall_status.value in ("FAILED", "ERROR"):
        raise typer.Exit(code=1)


# ── Deploy up / down / restart ───────────────────────────────────────────


@app.command("up")
def deploy_up(
    target: list[str] = typer.Option([], "--target", "-t", help="Specific service(s) to start."),
    profile: str = typer.Option("apps", "--profile", "-p", help="Docker Compose profile."),
    compose_file: list[str] = typer.Option(
        [], "--file", "-f", help="Docker Compose file(s). Repeatable.",
    ),
    build: bool = typer.Option(False, "--build", help="Build images before starting."),
    detach: bool = typer.Option(True, "--detach/--no-detach", "-d", help="Run in background."),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait and check health after start."),
    project: str | None = typer.Option(None, "--project-name", help="Docker Compose project name."),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Start Spine ecosystem services.

    Launches services using Docker Compose with the specified profile.
    """
    from spine.deploy.config import DeploymentConfig, DeploymentMode
    from spine.deploy.workflow import DeploymentRunner

    config = DeploymentConfig(
        mode=DeploymentMode.UP,
        targets=target,
        profile=profile,
        compose_files=compose_file,
        build=build,
        detach=detach,
        wait=wait,
        project_name=project,
    )

    console.print(f"[bold green]▲ deploy up[/] — profile: {profile}")
    runner = DeploymentRunner(config)
    result = runner.run()

    if json_out:
        typer.echo(result.model_dump_json(indent=2))
    else:
        _print_deployment_result(result)

    if result.error:
        raise typer.Exit(code=1)


@app.command("down")
def deploy_down(
    compose_file: list[str] = typer.Option(
        [], "--file", "-f", help="Docker Compose file(s).",
    ),
    project: str | None = typer.Option(None, "--project-name", help="Project name."),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Stop Spine ecosystem services."""
    from spine.deploy.config import DeploymentConfig, DeploymentMode
    from spine.deploy.workflow import DeploymentRunner

    config = DeploymentConfig(
        mode=DeploymentMode.DOWN,
        compose_files=compose_file,
        project_name=project,
    )

    console.print("[bold red]▼ deploy down[/]")
    runner = DeploymentRunner(config)
    result = runner.run()

    if json_out:
        typer.echo(result.model_dump_json(indent=2))
    else:
        console.print("[green]✓ Services stopped[/]" if not result.error else f"[red]✗ {result.error}[/]")

    if result.error:
        raise typer.Exit(code=1)


@app.command("status")
def deploy_status(
    compose_file: list[str] = typer.Option(
        [], "--file", "-f", help="Docker Compose file(s).",
    ),
    project: str | None = typer.Option(None, "--project-name", help="Project name."),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Check status of deployed services."""
    from spine.deploy.config import DeploymentConfig, DeploymentMode
    from spine.deploy.workflow import DeploymentRunner

    config = DeploymentConfig(
        mode=DeploymentMode.STATUS,
        compose_files=compose_file,
        project_name=project,
    )

    runner = DeploymentRunner(config)
    result = runner.run()

    if json_out:
        typer.echo(result.model_dump_json(indent=2))
    else:
        _print_deployment_result(result)


@app.command("restart")
def deploy_restart(
    target: list[str] = typer.Option([], "--target", "-t", help="Specific service(s)."),
    compose_file: list[str] = typer.Option(
        [], "--file", "-f", help="Docker Compose file(s).",
    ),
    project: str | None = typer.Option(None, "--project-name", help="Project name."),
) -> None:
    """Restart Spine ecosystem services (down then up)."""
    from spine.deploy.config import DeploymentConfig, DeploymentMode
    from spine.deploy.workflow import DeploymentRunner

    config = DeploymentConfig(
        mode=DeploymentMode.RESTART,
        targets=target,
        compose_files=compose_file,
        project_name=project,
    )

    console.print("[bold yellow]↻ deploy restart[/]")
    runner = DeploymentRunner(config)
    result = runner.run()

    if result.error:
        err_console.print(f"[red]✗ {result.error}[/]")
        raise typer.Exit(code=1)
    console.print("[green]✓ Services restarted[/]")


# ── Logs ─────────────────────────────────────────────────────────────────


@app.command("logs")
def deploy_logs(
    service: str | None = typer.Option(None, "--service", "-s", help="Service name."),
    tail: int = typer.Option(100, "--tail", "-n", help="Number of lines."),
    compose_file: list[str] = typer.Option(
        [], "--file", "-f", help="Docker Compose file(s).",
    ),
) -> None:
    """Show logs from deployed services."""
    import subprocess

    cmd = ["docker", "compose"]
    if compose_file:
        for f in compose_file:
            cmd.extend(["-f", f])
    cmd.extend(["logs", "--tail", str(tail)])

    if service:
        cmd.append(service)

    try:
        subprocess.run(cmd, check=False)  # noqa: S603
    except FileNotFoundError:
        err_console.print("[red]Docker is not available.[/]")
        raise typer.Exit(code=1)


# ── Info commands ────────────────────────────────────────────────────────


@app.command("backends")
def list_backends(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List available database backends."""
    from spine.deploy.backends import BACKENDS

    if json_out:
        out = {
            name: {
                "dialect": spec.dialect,
                "image": spec.image or "none (in-process)",
                "port": spec.port,
                "requires_license": spec.requires_license,
            }
            for name, spec in BACKENDS.items()
        }
        typer.echo(json.dumps(out, indent=2))
        return

    table = Table(title="Available Backends")
    table.add_column("Name", style="bold cyan")
    table.add_column("Dialect")
    table.add_column("Image")
    table.add_column("Port")
    table.add_column("License")

    for name, spec in BACKENDS.items():
        table.add_row(
            name,
            spec.dialect,
            spec.image or "(in-process)",
            str(spec.port or "—"),
            "required" if spec.requires_license else "—",
        )

    console.print(table)


@app.command("services")
def list_services(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List available services."""
    from spine.deploy.backends import SERVICES

    if json_out:
        out = {
            name: {
                "image": spec.image,
                "port": spec.port,
                "profiles": spec.compose_profiles,
                "healthcheck_url": spec.healthcheck_url,
            }
            for name, spec in SERVICES.items()
        }
        typer.echo(json.dumps(out, indent=2))
        return

    table = Table(title="Available Services")
    table.add_column("Name", style="bold cyan")
    table.add_column("Image")
    table.add_column("Port")
    table.add_column("Profiles")
    table.add_column("Healthcheck")

    for name, spec in SERVICES.items():
        table.add_row(
            name,
            spec.image,
            str(spec.port),
            ", ".join(spec.compose_profiles) if spec.compose_profiles else "—",
            spec.healthcheck_url or "—",
        )

    console.print(table)


@app.command("clean")
def clean(
    prefix: str = typer.Option("spine-testbed", "--prefix", help="Container name prefix."),
) -> None:
    """Remove orphaned testbed containers and networks."""
    from spine.deploy.container import ContainerManager

    if not ContainerManager.is_docker_available():
        err_console.print("[red]Docker is not available.[/]")
        raise typer.Exit(code=1)

    mgr = ContainerManager(network_prefix=prefix)
    removed = mgr.cleanup_orphans()
    console.print(f"[green]Removed {removed} orphaned containers/networks.[/]")


# ── Output formatters ────────────────────────────────────────────────────


def _print_testbed_result(result: object) -> None:
    """Pretty-print a TestbedRunResult."""
    from spine.deploy.results import OverallStatus

    table = Table(title="Testbed Results")
    table.add_column("Backend", style="bold")
    table.add_column("Status")
    table.add_column("Schema")
    table.add_column("Tests")
    table.add_column("Examples")
    table.add_column("Time")
    table.add_column("Error")

    for br in result.backends:  # type: ignore[attr-defined]
        status_style = {
            OverallStatus.PASSED: "green",
            OverallStatus.FAILED: "red",
            OverallStatus.PARTIAL: "yellow",
            OverallStatus.ERROR: "red bold",
            OverallStatus.SKIPPED: "dim",
        }.get(br.overall_status, "white")

        schema_str = "—"
        if br.schema_result:
            schema_str = f"{br.schema_result.tables_created}/{br.schema_result.tables_expected}"

        test_str = "—"
        if br.tests:
            test_str = f"{br.tests.passed}/{br.tests.total}"

        example_str = "—"
        if br.examples:
            example_str = f"{br.examples.passed}/{br.examples.total}"

        table.add_row(
            br.backend,
            f"[{status_style}]{br.overall_status.value}[/{status_style}]",
            schema_str,
            test_str,
            example_str,
            f"{br.startup_ms:.0f}ms" if br.startup_ms else "—",
            br.error or "—",
        )

    console.print(table)

    # Summary line
    r = result  # type: ignore[attr-defined]
    style = "green" if r.overall_status == OverallStatus.PASSED else "red"
    console.print(f"\n[bold {style}]{r.overall_status.value}[/] — {r.summary}")


def _print_deployment_result(result: object) -> None:
    """Pretty-print a DeploymentResult."""
    table = Table(title="Service Status")
    table.add_column("Service", style="bold")
    table.add_column("Status")
    table.add_column("Container")
    table.add_column("Image")

    for svc in result.services:  # type: ignore[attr-defined]
        status_style = {
            "running": "green",
            "healthy": "green bold",
            "starting": "yellow",
            "unhealthy": "red",
            "exited": "red",
            "not_found": "dim",
        }.get(svc.status, "white")

        table.add_row(
            svc.name,
            f"[{status_style}]{svc.status}[/{status_style}]",
            svc.container_name or "—",
            svc.image or "—",
        )

    console.print(table)

    if result.error:  # type: ignore[attr-defined]
        err_console.print(f"\n[red]Error: {result.error}[/]")  # type: ignore[attr-defined]
