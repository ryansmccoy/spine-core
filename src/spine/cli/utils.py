"""
CLI utility helpers — output formatting and connection management.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError as e:  # pragma: no cover
    raise SystemExit("Missing CLI deps.  Install with:  pip install spine-core[cli]") from e

from spine.ops.context import OperationContext
from spine.ops.result import OperationResult, PagedResult
from spine.ops.sqlite_conn import SqliteConnection

console = Console()
err_console = Console(stderr=True)


# ── Connection helper ────────────────────────────────────────────────────


def get_connection(database: str | None = None) -> Any:
    """Open a database connection.  Defaults to ``~/.spine/spine_core.db``."""
    db_path = database or str(Path.home() / ".spine" / "spine_core.db")
    return SqliteConnection(db_path)


def make_context(
    database: str | None = None,
    *,
    dry_run: bool = False,
) -> tuple[OperationContext, Any]:
    """Create an ``OperationContext`` + connection pair for CLI commands."""
    conn = get_connection(database)
    ctx = OperationContext(conn=conn, caller="cli", dry_run=dry_run)
    return ctx, conn


# ── Output helpers ───────────────────────────────────────────────────────


def _to_dict(obj: Any) -> dict[str, Any]:
    """Convert dataclass / pydantic model / dict to plain dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    return {"value": str(obj)}


def output_result(
    result: OperationResult,
    *,
    as_json: bool = False,
    title: str = "",
) -> None:
    """Render an ``OperationResult`` to the terminal."""
    if not result.success:
        err = result.error
        msg = err.message if err else "Unknown error"
        code = err.code if err else "ERROR"
        err_console.print(f"[bold red]Error[/bold red] ({code}): {msg}")
        raise typer.Exit(code=1)

    data = result.data

    if as_json:
        payload = _to_dict(data) if not isinstance(data, list | tuple) else [_to_dict(d) for d in data]
        console.print_json(json.dumps(payload, default=str))
        return

    if isinstance(data, list):
        if not data:
            console.print("[dim]No items.[/dim]")
            return
        _print_table(data, title=title)
    else:
        _print_dict(_to_dict(data), title=title)


def output_paged(
    result: PagedResult,
    *,
    as_json: bool = False,
    title: str = "",
) -> None:
    """Render a ``PagedResult`` to the terminal with pagination info."""
    if not result.success:
        err = result.error
        msg = err.message if err else "Unknown error"
        code = err.code if err else "ERROR"
        err_console.print(f"[bold red]Error[/bold red] ({code}): {msg}")
        raise typer.Exit(code=1)

    items = result.data or []

    if as_json:
        payload = {
            "items": [_to_dict(d) for d in items],
            "total": result.total,
            "limit": result.limit,
            "offset": result.offset,
            "has_more": result.has_more,
        }
        console.print_json(json.dumps(payload, default=str))
        return

    if not items:
        console.print("[dim]No items.[/dim]")
        return

    _print_table(items, title=title)

    if result.total is not None:
        console.print(
            f"\n[dim]Showing {len(items)} of {result.total}"
            f" (offset {result.offset})[/dim]"
        )


# ── Private helpers ──────────────────────────────────────────────────────


def _print_table(items: list, *, title: str = "") -> None:
    """Render a list of dataclasses/dicts as a Rich table."""
    first = _to_dict(items[0])
    table = Table(title=title or None, show_lines=False, pad_edge=False)
    for col in first:
        table.add_column(col, overflow="fold")
    for item in items:
        d = _to_dict(item)
        table.add_row(*(str(v) for v in d.values()))
    console.print(table)


def _print_dict(data: dict[str, Any], *, title: str = "") -> None:
    """Render a single dict as key-value pairs."""
    if title:
        console.print(f"[bold]{title}[/bold]")
    for k, v in data.items():
        console.print(f"  [cyan]{k}[/cyan]: {v}")
