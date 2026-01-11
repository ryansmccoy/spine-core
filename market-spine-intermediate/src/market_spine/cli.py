"""CLI entry point for Market Spine."""

import json
import sys
from pathlib import Path

import click
import structlog

from market_spine.config import get_settings
from market_spine.db import init_db
from market_spine.registry import registry
from market_spine.runner import run_pipeline_sync
from market_spine.dispatcher import Dispatcher

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger()


@click.group()
@click.version_option(version="0.2.0")
def cli():
    """Market Spine - Analytics Pipeline Orchestration."""
    pass


# -------------------------------------------------------------------------
# Database Commands
# -------------------------------------------------------------------------


@cli.group()
def db():
    """Database management commands."""
    pass


@db.command("init")
def db_init():
    """Initialize the database schema."""
    click.echo("Initializing database...")
    init_db()
    click.echo("Database initialized successfully.")


@db.command("migrate")
def db_migrate():
    """Run database migrations."""
    click.echo("Running migrations...")
    init_db()
    click.echo("Migrations complete.")


# -------------------------------------------------------------------------
# Pipeline Commands
# -------------------------------------------------------------------------


@cli.group()
def pipeline():
    """Pipeline management commands."""
    pass


@pipeline.command("list")
def pipeline_list():
    """List available pipelines."""
    pipelines = registry.list_pipelines()

    if not pipelines:
        click.echo("No pipelines registered.")
        return

    click.echo("\nAvailable Pipelines:")
    click.echo("-" * 60)
    for p in pipelines:
        click.echo(f"  {p['name']:<25} {p['description']}")
    click.echo()


@pipeline.command("run")
@click.argument("name")
@click.option("--params", "-p", help="JSON parameters")
@click.option("--file-path", "-f", help="File path parameter (convenience)")
@click.option("--symbol", "-s", help="Symbol parameter (convenience)")
@click.option("--date", "-d", help="Date parameter (convenience)")
def pipeline_run(
    name: str, params: str | None, file_path: str | None, symbol: str | None, date: str | None
):
    """
    Run a pipeline synchronously.

    Examples:
        spine pipeline run otc.ingest -f data/otc_sample.csv
        spine pipeline run otc.normalize
        spine pipeline run otc.compute --symbol ACME
    """
    # Parse params
    pipeline_params = {}
    if params:
        try:
            pipeline_params = json.loads(params)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON parameters: {e}", err=True)
            sys.exit(1)

    # Apply convenience options
    if file_path:
        pipeline_params["file_path"] = file_path
    if symbol:
        pipeline_params["symbol"] = symbol
    if date:
        pipeline_params["date"] = date

    # Initialize DB
    init_db()

    # Run
    click.echo(f"Running pipeline: {name}")
    try:
        result = run_pipeline_sync(name, pipeline_params)
        click.echo(f"\nResult: {json.dumps(result, indent=2, default=str)}")
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


@pipeline.command("submit")
@click.argument("name")
@click.option("--params", "-p", help="JSON parameters")
@click.option("--logical-key", "-k", help="Logical key for concurrency control")
def pipeline_submit(name: str, params: str | None, logical_key: str | None):
    """
    Submit a pipeline for async execution.

    Returns immediately with the execution ID.
    """
    pipeline_params = {}
    if params:
        try:
            pipeline_params = json.loads(params)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON parameters: {e}", err=True)
            sys.exit(1)

    # Initialize DB
    init_db()

    # Submit
    dispatcher = Dispatcher()
    try:
        execution_id = dispatcher.submit(name, pipeline_params, logical_key)
        click.echo(f"Submitted: {execution_id}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# -------------------------------------------------------------------------
# Worker Commands
# -------------------------------------------------------------------------


@cli.command("worker")
def worker():
    """Start the background worker."""
    from market_spine.orchestration.worker import run_worker

    # Initialize DB
    init_db()

    # Run worker
    run_worker()


# -------------------------------------------------------------------------
# API Commands
# -------------------------------------------------------------------------


@cli.command("serve")
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host: str, port: int, reload: bool):
    """Start the API server."""
    import uvicorn

    click.echo(f"Starting API server on {host}:{port}")
    uvicorn.run(
        "market_spine.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


# -------------------------------------------------------------------------
# Metrics Commands
# -------------------------------------------------------------------------


@cli.group()
def metrics():
    """Query metrics data."""
    pass


@metrics.command("list")
@click.option("--symbol", "-s", help="Filter by symbol")
@click.option("--limit", "-n", default=20, help="Number of results")
def metrics_list(symbol: str | None, limit: int):
    """List daily metrics."""
    from market_spine.repositories.otc import OTCRepository

    init_db()

    repo = OTCRepository()
    results = repo.get_daily_metrics(symbol=symbol, limit=limit)

    if not results:
        click.echo("No metrics found.")
        return

    click.echo(f"\n{'Symbol':<10} {'Date':<12} {'VWAP':>12} {'Volume':>12} {'Count':>8}")
    click.echo("-" * 60)
    for m in results:
        click.echo(
            f"{m['symbol']:<10} {str(m['date']):<12} "
            f"{float(m['vwap']):>12.4f} {float(m['total_volume']):>12.0f} "
            f"{m['trade_count']:>8}"
        )


@metrics.command("vwap")
@click.argument("symbol")
@click.argument("date")
def metrics_vwap(symbol: str, date: str):
    """Get VWAP for a symbol and date."""
    from datetime import datetime
    from market_spine.services.otc_metrics import OTCMetricsCalculator

    init_db()

    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        click.echo("Error: Invalid date format. Use YYYY-MM-DD", err=True)
        sys.exit(1)

    calculator = OTCMetricsCalculator()
    vwap = calculator.get_vwap(symbol.upper(), target_date)

    if vwap is None:
        click.echo(f"No VWAP available for {symbol.upper()} on {date}")
    else:
        click.echo(f"VWAP for {symbol.upper()} on {date}: {float(vwap):.6f}")


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
