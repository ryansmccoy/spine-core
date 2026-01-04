"""Modern CLI for Market Spine using Typer."""

from typing import Optional

import typer
from typing_extensions import Annotated

# Configure logging FIRST, before any imports that trigger pipeline registration
# This prevents debug logs from appearing during --help and --version
from spine.framework.logging import configure_logging
configure_logging()  # Uses SPINE_LOG_LEVEL env var (default: INFO)

from market_spine import __version__
from market_spine.db import init_connection_provider

from .commands import db, doctor, list_, query, run, verify

# Initialize database connection provider once at CLI startup
init_connection_provider()
from .console import console
from .logging_config import LogDestination, LogFormat, configure_cli_logging

# Create main Typer app
app = typer.Typer(
    name="spine",
    help="Market Spine - Analytics Pipeline System",
    add_completion=False,  # We'll add this later if needed
    no_args_is_help=False,  # We want to handle no-args specially for interactive mode
    rich_markup_mode="rich",
)

# Add command groups
app.add_typer(list_.app, name="pipelines", help="Discover and inspect pipelines")
app.add_typer(run.app, name="run", help="Execute pipeline operations")
app.add_typer(query.app, name="query", help="Query processed data")
app.add_typer(verify.app, name="verify", help="Verify database integrity")
app.add_typer(db.app, name="db", help="Database management")
app.add_typer(doctor.app, name="doctor", help="System health checks")


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"spine, version {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", callback=version_callback, help="Show version and exit"),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging level"),
    ] = "INFO",
    log_format: Annotated[
        LogFormat,
        typer.Option("--log-format", help="Log format"),
    ] = LogFormat.PRETTY,
    log_to: Annotated[
        LogDestination,
        typer.Option("--log-to", help="Log destination"),
    ] = LogDestination.STDOUT,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress logs, show only summary"),
    ] = False,
) -> None:
    """
    Market Spine - Analytics Pipeline System.
    
    Run without arguments to enter interactive mode.
    """
    # Configure logging based on options
    configure_cli_logging(
        log_level=log_level.upper(),
        log_format=log_format,
        log_to=log_to,
        quiet=quiet,
    )


@app.command(name="ui", hidden=True)
def interactive_ui() -> None:
    """Launch interactive UI (alias for running with no args)."""
    from .interactive.menu import run_interactive_menu

    run_interactive_menu()


# Handle no-args case for interactive mode
def cli_main() -> None:
    """Main entry point that handles no-args for interactive mode."""
    import sys

    # If no arguments provided, launch interactive mode
    if len(sys.argv) == 1:
        from .interactive.menu import run_interactive_menu

        try:
            run_interactive_menu()
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled[/yellow]")
            sys.exit(0)
    else:
        app()


if __name__ == "__main__":
    cli_main()
