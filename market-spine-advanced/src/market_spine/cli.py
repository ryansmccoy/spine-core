"""CLI for Market Spine Advanced."""

import json
from datetime import date
from typing import Optional

import typer
import structlog

from market_spine.config import get_settings
from market_spine.db import init_pool, close_pool

app = typer.Typer(
    name="market-spine",
    help="Market Spine Advanced - Analytics Pipeline System",
    no_args_is_help=True,
)

logger = structlog.get_logger()


def setup():
    """Initialize application."""
    settings = get_settings()
    init_pool(settings.database_url)


def teardown():
    """Cleanup application."""
    close_pool()


# =============================================================================
# Database Commands
# =============================================================================

db_app = typer.Typer(help="Database operations")
app.add_typer(db_app, name="db")


@db_app.command("migrate")
def db_migrate(
    migrations_dir: str = typer.Option(
        "migrations",
        help="Directory containing migration files",
    ),
):
    """Run database migrations."""
    from pathlib import Path
    import psycopg

    settings = get_settings()
    migrations_path = Path(migrations_dir)

    if not migrations_path.exists():
        typer.echo(f"Migrations directory not found: {migrations_path}")
        raise typer.Exit(1)

    # Get migration files
    migration_files = sorted(migrations_path.glob("*.sql"))

    if not migration_files:
        typer.echo("No migration files found")
        return

    typer.echo(f"Found {len(migration_files)} migration files")

    with psycopg.connect(settings.database_url) as conn:
        # Create migrations tracking table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # Get applied migrations
        result = conn.execute("SELECT filename FROM _migrations")
        applied = {row[0] for row in result.fetchall()}

        for migration_file in migration_files:
            if migration_file.name in applied:
                typer.echo(f"  [skip] {migration_file.name}")
                continue

            typer.echo(f"  [apply] {migration_file.name}")
            sql = migration_file.read_text()
            conn.execute(sql)
            conn.execute(
                "INSERT INTO _migrations (filename) VALUES (%s)",
                (migration_file.name,),
            )

        conn.commit()

    typer.echo("Migrations complete")


# =============================================================================
# Pipeline Commands
# =============================================================================

pipeline_app = typer.Typer(help="Pipeline operations")
app.add_typer(pipeline_app, name="pipeline")


@pipeline_app.command("list")
def pipeline_list():
    """List available pipelines."""
    setup()
    try:
        from market_spine.pipelines import PipelineRegistry

        pipelines = PipelineRegistry.list_pipelines()

        if not pipelines:
            typer.echo("No pipelines registered")
            return

        typer.echo("\nAvailable Pipelines:")
        typer.echo("-" * 60)
        for p in pipelines:
            typer.echo(f"  {p['name']:<20} {p['description']}")
    finally:
        teardown()


@pipeline_app.command("run")
def pipeline_run(
    name: str = typer.Argument(..., help="Pipeline name"),
    params: str = typer.Option("{}", help="JSON parameters"),
    sync: bool = typer.Option(False, "--sync", help="Run synchronously"),
):
    """Submit a pipeline for execution."""
    setup()
    try:
        params_dict = json.loads(params)

        if sync:
            from market_spine.pipelines import PipelineRunner

            typer.echo(f"Running {name} synchronously...")
            from market_spine.repositories.executions import ExecutionRepository

            exec_id = ExecutionRepository.create(name, params_dict)
            result = PipelineRunner.run(exec_id, name, params_dict)

            if result.success:
                typer.echo(f"✓ Pipeline completed in {result.total_duration_ms:.0f}ms")
                if result.output:
                    typer.echo(f"  Output: {json.dumps(result.output, default=str)}")
            else:
                typer.echo(f"✗ Pipeline failed: {result.error}")
                raise typer.Exit(1)
        else:
            from market_spine.dispatcher import Dispatcher

            execution_id = Dispatcher.submit(name, params_dict)
            typer.echo(f"Submitted execution: {execution_id}")
    finally:
        teardown()


@pipeline_app.command("status")
def pipeline_status(execution_id: str = typer.Argument(..., help="Execution ID")):
    """Get execution status."""
    setup()
    try:
        from market_spine.dispatcher import Dispatcher

        execution = Dispatcher.get_status(execution_id)
        if not execution:
            typer.echo(f"Execution not found: {execution_id}")
            raise typer.Exit(1)

        typer.echo(f"\nExecution: {execution_id}")
        typer.echo("-" * 60)
        typer.echo(f"  Pipeline: {execution['pipeline_name']}")
        typer.echo(f"  Status:   {execution['status']}")
        typer.echo(f"  Backend:  {execution.get('backend', 'N/A')}")
        typer.echo(f"  Retries:  {execution['retry_count']}")
        typer.echo(f"  Created:  {execution['created_at']}")

        if execution.get("started_at"):
            typer.echo(f"  Started:  {execution['started_at']}")
        if execution.get("completed_at"):
            typer.echo(f"  Completed: {execution['completed_at']}")
        if execution.get("error_message"):
            typer.echo(f"  Error:    {execution['error_message']}")
    finally:
        teardown()


# =============================================================================
# DLQ Commands
# =============================================================================

dlq_app = typer.Typer(help="Dead Letter Queue operations")
app.add_typer(dlq_app, name="dlq")


@dlq_app.command("list")
def dlq_list(
    limit: int = typer.Option(50, help="Maximum items to show"),
    retryable: bool = typer.Option(False, "--retryable", help="Show only retryable items"),
):
    """List DLQ items."""
    setup()
    try:
        from market_spine.orchestration import DLQManager

        if retryable:
            items = DLQManager.get_retryable(limit)
        else:
            items = DLQManager.list_dlq(limit)

        if not items:
            typer.echo("DLQ is empty")
            return

        typer.echo(f"\nDLQ Items ({len(items)}):")
        typer.echo("-" * 80)
        for item in items:
            retry_str = "✓" if item.get("can_retry") else "✗"
            typer.echo(
                f"  [{retry_str}] {item['id'][:12]}... | "
                f"{item['pipeline_name']} | "
                f"retries: {item['retry_count']} | "
                f"{item.get('error_message', 'N/A')[:40]}"
            )
    finally:
        teardown()


@dlq_app.command("retry")
def dlq_retry(
    execution_id: str = typer.Argument(..., help="Execution ID to retry"),
):
    """Retry a DLQ item."""
    setup()
    try:
        from market_spine.orchestration import DLQManager

        new_id = DLQManager.retry(execution_id)
        if new_id:
            typer.echo(f"Retried: {execution_id} → {new_id}")
        else:
            typer.echo(f"Cannot retry execution: {execution_id}")
            raise typer.Exit(1)
    finally:
        teardown()


@dlq_app.command("retry-all")
def dlq_retry_all(
    limit: int = typer.Option(100, help="Maximum items to retry"),
):
    """Retry all retryable DLQ items."""
    setup()
    try:
        from market_spine.orchestration import DLQManager

        retried = DLQManager.auto_retry(limit)
        typer.echo(f"Retried {retried} items")
    finally:
        teardown()


# =============================================================================
# Schedule Commands
# =============================================================================

schedule_app = typer.Typer(help="Pipeline scheduling")
app.add_typer(schedule_app, name="schedule")


@schedule_app.command("list")
def schedule_list(
    enabled_only: bool = typer.Option(False, "--enabled", help="Show only enabled"),
):
    """List schedules."""
    setup()
    try:
        from market_spine.orchestration import ScheduleManager

        schedules = ScheduleManager.list_schedules(enabled_only)

        if not schedules:
            typer.echo("No schedules configured")
            return

        typer.echo("\nSchedules:")
        typer.echo("-" * 80)
        for s in schedules:
            status = "✓" if s["enabled"] else "✗"
            typer.echo(
                f"  [{status}] {s['id'][:12]}... | "
                f"{s['pipeline_name']} | "
                f"{s['cron_expression']} | "
                f"next: {s.get('next_run_at', 'N/A')}"
            )
    finally:
        teardown()


@schedule_app.command("create")
def schedule_create(
    pipeline_name: str = typer.Argument(..., help="Pipeline to schedule"),
    cron: str = typer.Argument(..., help="Cron expression (e.g., '0 9 * * *')"),
    params: str = typer.Option("{}", help="JSON parameters"),
):
    """Create a new schedule."""
    setup()
    try:
        from market_spine.orchestration import ScheduleManager

        params_dict = json.loads(params)
        schedule_id = ScheduleManager.create_schedule(pipeline_name, cron, params_dict)
        typer.echo(f"Created schedule: {schedule_id}")
    except ValueError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1)
    finally:
        teardown()


@schedule_app.command("delete")
def schedule_delete(schedule_id: str = typer.Argument(..., help="Schedule ID")):
    """Delete a schedule."""
    setup()
    try:
        from market_spine.orchestration import ScheduleManager

        if ScheduleManager.delete_schedule(schedule_id):
            typer.echo(f"Deleted schedule: {schedule_id}")
        else:
            typer.echo(f"Schedule not found: {schedule_id}")
            raise typer.Exit(1)
    finally:
        teardown()


@schedule_app.command("enable")
def schedule_enable(schedule_id: str = typer.Argument(..., help="Schedule ID")):
    """Enable a schedule."""
    setup()
    try:
        from market_spine.orchestration import ScheduleManager

        if ScheduleManager.enable_schedule(schedule_id):
            typer.echo(f"Enabled schedule: {schedule_id}")
        else:
            typer.echo(f"Schedule not found: {schedule_id}")
            raise typer.Exit(1)
    finally:
        teardown()


@schedule_app.command("disable")
def schedule_disable(schedule_id: str = typer.Argument(..., help="Schedule ID")):
    """Disable a schedule."""
    setup()
    try:
        from market_spine.orchestration import ScheduleManager

        if ScheduleManager.disable_schedule(schedule_id):
            typer.echo(f"Disabled schedule: {schedule_id}")
        else:
            typer.echo(f"Schedule not found: {schedule_id}")
            raise typer.Exit(1)
    finally:
        teardown()


@schedule_app.command("trigger")
def schedule_trigger():
    """Check and trigger due schedules."""
    setup()
    try:
        from market_spine.orchestration import ScheduleManager

        triggered = ScheduleManager.trigger_due_schedules()
        typer.echo(f"Triggered {triggered} schedules")
    finally:
        teardown()


# =============================================================================
# Worker Commands
# =============================================================================

worker_app = typer.Typer(help="Celery worker management")
app.add_typer(worker_app, name="worker")


@worker_app.command("start")
def worker_start(
    concurrency: int = typer.Option(4, help="Number of worker processes"),
    queues: str = typer.Option("celery", help="Comma-separated queue names"),
    loglevel: str = typer.Option("INFO", help="Log level"),
):
    """Start Celery worker."""
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "market_spine.celery_app",
        "worker",
        f"--concurrency={concurrency}",
        f"--queues={queues}",
        f"--loglevel={loglevel}",
    ]

    typer.echo(f"Starting worker: {' '.join(cmd)}")
    subprocess.run(cmd)


@worker_app.command("beat")
def worker_beat(
    loglevel: str = typer.Option("INFO", help="Log level"),
):
    """Start Celery beat scheduler."""
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "market_spine.celery_app",
        "beat",
        f"--loglevel={loglevel}",
    ]

    typer.echo(f"Starting beat: {' '.join(cmd)}")
    subprocess.run(cmd)


# =============================================================================
# Server Commands
# =============================================================================


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to bind"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
):
    """Start the API server."""
    import uvicorn

    uvicorn.run(
        "market_spine.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


# =============================================================================
# Main
# =============================================================================


def main():
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
