"""
CLI: ``spine-core serve`` — start the API server.
"""

from __future__ import annotations

import typer

from spine.cli.utils import console

app = typer.Typer(no_args_is_help=True)


@app.command("start")
def start(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind address"),
    port: int = typer.Option(12000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on changes"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of workers"),
    log_level: str = typer.Option("info", "--log-level"),
) -> None:
    """Start the spine-core REST API server."""
    try:
        import uvicorn
    except ImportError as e:
        console.print("[red]uvicorn is required.  Install with:  pip install spine-core[api][/red]")
        raise typer.Exit(code=1) from e

    console.print(f"[bold green]Starting spine-core API[/bold green] on {host}:{port}")
    uvicorn.run(
        "spine.api:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level=log_level,
    )
