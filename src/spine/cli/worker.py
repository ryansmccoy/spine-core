"""
CLI: ``spine-core worker`` — start the background execution worker.
"""

from __future__ import annotations

import typer

from spine.cli.utils import console

app = typer.Typer(no_args_is_help=True)


@app.command("start")
def start(
    db: str = typer.Option("spine.db", "--db", "-d", help="SQLite database path"),
    workers: int = typer.Option(4, "--workers", "-w", help="Concurrent execution threads"),
    poll_interval: float = typer.Option(2.0, "--poll-interval", help="Seconds between poll cycles"),
    batch_size: int = typer.Option(10, "--batch-size", help="Max runs to claim per poll"),
    worker_id: str | None = typer.Option(None, "--id", help="Custom worker identifier"),  # noqa: UP007
) -> None:
    """Start the background worker to process pending execution runs.

    The worker polls the database for runs with status='pending', claims them,
    and dispatches to registered handlers via the HandlerRegistry.

    Example::

        spine-core worker start --workers 4 --poll-interval 2
        spine-core worker start --db /data/spine.db --batch-size 20
    """
    from spine.execution.worker import WorkerLoop

    console.print(
        f"[bold green]Starting spine-core worker[/bold green] "
        f"(threads={workers}, poll={poll_interval}s, batch={batch_size})"
    )

    try:
        loop = WorkerLoop(
            db_path=db,
            poll_interval=poll_interval,
            batch_size=batch_size,
            max_workers=workers,
            worker_id=worker_id,
        )
        loop.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker stopped by user[/yellow]")
    except Exception as exc:
        console.print(f"[red]Worker error: {exc}[/red]")
        raise typer.Exit(code=1)


@app.command("status")
def status() -> None:
    """Show active workers in this process (if running as library)."""
    from spine.execution.worker import get_active_workers

    workers = get_active_workers()
    if not workers:
        console.print("[yellow]No active workers found in this process[/yellow]")
        return

    for w in workers:
        console.print(f"  [bold]{w.worker_id}[/bold]  pid={w.pid}  status={w.status}  "
                      f"processed={w.runs_processed}  failed={w.runs_failed}")
