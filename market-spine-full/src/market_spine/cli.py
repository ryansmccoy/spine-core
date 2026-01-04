"""Market Spine CLI."""

import sys
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from market_spine.core.settings import get_settings

app = typer.Typer(
    name="spine",
    help="Market Spine analytics pipeline CLI",
    no_args_is_help=True,
)


# Database commands
db_app = typer.Typer(help="Database management commands")
app.add_typer(db_app, name="db")


@db_app.command("migrate")
def db_migrate(
    migrations_path: str = typer.Option("migrations", help="Path to migrations directory"),
):
    """Run database migrations."""
    from market_spine.core.database import get_pool

    migrations_dir = Path(migrations_path)
    if not migrations_dir.exists():
        typer.echo(f"Migrations directory not found: {migrations_dir}", err=True)
        raise typer.Exit(1)

    # Get migration files
    migration_files = sorted(migrations_dir.glob("*.sql"))
    if not migration_files:
        typer.echo("No migration files found")
        return

    typer.echo(f"Found {len(migration_files)} migration files")

    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            # Create migrations table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT NOW()
                )
            """)
            conn.commit()

            # Get applied migrations
            cur.execute("SELECT name FROM _migrations")
            applied = {row[0] for row in cur.fetchall()}

            # Apply new migrations
            for migration_file in migration_files:
                if migration_file.name in applied:
                    typer.echo(f"  Skipping: {migration_file.name}")
                    continue

                typer.echo(f"  Applying: {migration_file.name}")
                sql = migration_file.read_text()

                try:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO _migrations (name) VALUES (%s)",
                        (migration_file.name,),
                    )
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    typer.echo(f"  Error: {e}", err=True)
                    raise typer.Exit(1)

    typer.echo("Migrations complete")


@db_app.command("reset")
def db_reset(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Reset database (drop all tables)."""
    if not confirm:
        confirm = typer.confirm("This will drop all tables. Continue?")
        if not confirm:
            raise typer.Abort()

    from market_spine.core.database import get_pool

    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DO $$ DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
            """)
            conn.commit()

    typer.echo("Database reset complete")


# Pipeline commands
pipeline_app = typer.Typer(help="Pipeline management commands")
app.add_typer(pipeline_app, name="pipeline")


@pipeline_app.command("list")
def pipeline_list():
    """List available pipelines."""
    from market_spine.pipelines.registry import get_registry

    registry = get_registry()
    for pipeline in registry.all_definitions():
        lock_indicator = " 🔒" if pipeline.requires_lock else ""
        typer.echo(f"  {pipeline.name}{lock_indicator}")
        if pipeline.description:
            typer.echo(f"    {pipeline.description}")


@pipeline_app.command("run")
def pipeline_run(
    pipeline: str = typer.Argument(..., help="Pipeline name"),
    param: list[str] = typer.Option([], "--param", "-p", help="Parameters (key=value)"),
):
    """Run a pipeline directly (synchronous, bypasses queue)."""
    from market_spine.pipelines.registry import get_registry

    registry = get_registry()
    pipeline_def = registry.get(pipeline)

    if pipeline_def is None:
        typer.echo(f"Unknown pipeline: {pipeline}", err=True)
        raise typer.Exit(1)

    # Parse parameters
    params = {}
    for p in param:
        if "=" in p:
            key, value = p.split("=", 1)
            params[key] = value
        else:
            typer.echo(f"Invalid parameter format: {p}", err=True)
            raise typer.Exit(1)

    typer.echo(f"Running pipeline: {pipeline}")
    try:
        result = pipeline_def.handler(params)
        typer.echo(f"Result: {result}")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


# Dispatch command
@app.command("dispatch")
def dispatch(
    pipeline: str = typer.Argument(..., help="Pipeline name"),
    param: list[str] = typer.Option([], "--param", "-p", help="Parameters (key=value)"),
    lane: str = typer.Option("default", help="Execution lane"),
):
    """Submit a pipeline execution to the queue."""
    from market_spine.core.models import TriggerSource
    from market_spine.execution.ledger import ExecutionLedger
    from market_spine.execution.dispatcher import Dispatcher
    from market_spine.backends.celery_backend import CeleryBackend
    from market_spine.pipelines.registry import get_registry

    registry = get_registry()
    if registry.get(pipeline) is None:
        typer.echo(f"Unknown pipeline: {pipeline}", err=True)
        raise typer.Exit(1)

    # Parse parameters
    params = {}
    for p in param:
        if "=" in p:
            key, value = p.split("=", 1)
            params[key] = value

    ledger = ExecutionLedger()
    backend = CeleryBackend()
    dispatcher = Dispatcher(ledger, backend)

    execution = dispatcher.submit(
        pipeline=pipeline,
        params=params,
        lane=lane,
        trigger_source=TriggerSource.CLI,
    )

    typer.echo(f"Execution submitted: {execution.id}")


# Execution commands
execution_app = typer.Typer(help="Execution management commands")
app.add_typer(execution_app, name="execution")


@execution_app.command("status")
def execution_status(execution_id: str = typer.Argument(..., help="Execution ID")):
    """Check execution status."""
    from market_spine.execution.ledger import ExecutionLedger

    ledger = ExecutionLedger()
    execution = ledger.get_execution(execution_id)

    if execution is None:
        typer.echo("Execution not found", err=True)
        raise typer.Exit(1)

    typer.echo(f"Pipeline: {execution.pipeline}")
    typer.echo(f"Status: {execution.status.value}")
    typer.echo(f"Created: {execution.created_at}")
    if execution.started_at:
        typer.echo(f"Started: {execution.started_at}")
    if execution.completed_at:
        typer.echo(f"Completed: {execution.completed_at}")
    if execution.error:
        typer.echo(f"Error: {execution.error}")
    if execution.result:
        typer.echo(f"Result: {execution.result}")


@execution_app.command("list")
def execution_list(
    pipeline: Optional[str] = typer.Option(None, help="Filter by pipeline"),
    status: Optional[str] = typer.Option(None, help="Filter by status"),
    limit: int = typer.Option(20, help="Max results"),
):
    """List recent executions."""
    from market_spine.execution.ledger import ExecutionLedger
    from market_spine.core.models import ExecutionStatus

    ledger = ExecutionLedger()
    status_enum = ExecutionStatus(status) if status else None
    executions = ledger.list_executions(
        pipeline=pipeline,
        status=status_enum,
        limit=limit,
    )

    for ex in executions:
        typer.echo(f"{ex.id[:8]}... | {ex.pipeline:20} | {ex.status.value:10} | {ex.created_at}")


# Query commands
query_app = typer.Typer(help="Query data commands")
app.add_typer(query_app, name="query")


@query_app.command("metrics")
def query_metrics(
    symbol: str = typer.Argument(..., help="Symbol to query"),
    start: Optional[str] = typer.Option(None, help="Start date (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, help="End date (YYYY-MM-DD)"),
):
    """Query daily metrics for a symbol."""
    from market_spine.repositories.otc import OTCRepository

    start_date = date.fromisoformat(start) if start else None
    end_date = date.fromisoformat(end) if end else None

    repo = OTCRepository()
    metrics = repo.get_daily_metrics(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )

    if not metrics:
        typer.echo("No metrics found")
        return

    typer.echo(f"{'Date':12} | {'Trades':>8} | {'Volume':>12} | {'VWAP':>10}")
    typer.echo("-" * 50)
    for m in metrics:
        typer.echo(
            f"{str(m.date):12} | {m.trade_count:>8} | {m.total_volume:>12} | {float(m.vwap):>10.2f}"
        )


# Worker commands
@app.command("worker")
def worker_start(
    queues: str = typer.Option("default", help="Comma-separated queue names"),
    concurrency: int = typer.Option(4, help="Worker concurrency"),
    loglevel: str = typer.Option("info", help="Log level"),
):
    """Start Celery worker."""
    import subprocess

    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "market_spine.celery_app",
        "worker",
        "-Q",
        queues,
        "-c",
        str(concurrency),
        "-l",
        loglevel,
    ]
    subprocess.run(cmd)


@app.command("beat")
def beat_start(loglevel: str = typer.Option("info", help="Log level")):
    """Start Celery beat scheduler."""
    import subprocess

    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "market_spine.celery_app",
        "beat",
        "-l",
        loglevel,
    ]
    subprocess.run(cmd)


# Doctor command
@app.command("doctor")
def doctor():
    """Run system diagnostics."""
    typer.echo("Running diagnostics...\n")

    # Check database
    typer.echo("Database:")
    try:
        from market_spine.core.database import get_pool

        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
                typer.echo(f"  ✓ Connected: {version[:50]}...")

                # Check tables
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
                )
                table_count = cur.fetchone()[0]
                typer.echo(f"  ✓ Tables: {table_count}")
    except Exception as e:
        typer.echo(f"  ✗ Error: {e}")

    # Check Redis
    typer.echo("\nRedis:")
    try:
        import redis

        settings = get_settings()
        r = redis.from_url(settings.redis_url)
        info = r.info()
        typer.echo(f"  ✓ Connected: Redis {info['redis_version']}")
    except Exception as e:
        typer.echo(f"  ✗ Error: {e}")

    # Check executions
    typer.echo("\nExecution Stats:")
    try:
        from market_spine.execution.ledger import ExecutionLedger

        ledger = ExecutionLedger()
        stats = ledger.get_metrics()
        typer.echo(f"  Status counts: {stats.get('status_counts', {})}")
        typer.echo(f"  Recent (1h): {stats.get('recent_executions_1h', 0)}")
    except Exception as e:
        typer.echo(f"  ✗ Error: {e}")

    # Check DLQ
    typer.echo("\nDead Letter Queue:")
    try:
        from market_spine.execution.dlq import DLQManager

        dlq = DLQManager()
        entries = dlq.list_dead_letters(include_resolved=False)
        typer.echo(f"  Pending: {len(entries)}")
    except Exception as e:
        typer.echo(f"  ✗ Error: {e}")

    typer.echo("\nDiagnostics complete")


# Cleanup command
@app.command("cleanup")
def cleanup(
    older_than: str = typer.Option("90d", help="Age threshold (e.g., 30d, 12h)"),
    dry_run: bool = typer.Option(False, help="Don't actually delete"),
):
    """Clean up old executions and data."""
    from market_spine.repositories.execution import ExecutionRepository

    # Parse duration
    value = int(older_than[:-1])
    unit = older_than[-1]
    if unit == "d":
        days = value
    elif unit == "h":
        days = value / 24
    else:
        typer.echo("Invalid duration format. Use Nd or Nh", err=True)
        raise typer.Exit(1)

    typer.echo(f"Cleaning up data older than {days} days...")

    if dry_run:
        typer.echo("(Dry run - no changes will be made)")
        return

    repo = ExecutionRepository()
    executions_deleted = repo.cleanup_old_executions(days=int(days))
    dead_letters_deleted = repo.cleanup_old_dead_letters(days=int(days))

    typer.echo(f"Executions deleted: {executions_deleted}")
    typer.echo(f"Dead letters deleted: {dead_letters_deleted}")


if __name__ == "__main__":
    app()
