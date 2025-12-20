"""
CLI: ``spine-core anomaly`` — anomaly detection results commands.
"""

from __future__ import annotations

import typer

from spine.cli.utils import make_context, output_paged

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_anomalies(
    workflow: str | None = typer.Option(None, "--workflow", "-w"),
    severity: str | None = typer.Option(None, "--severity", "-s"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List anomaly detection results."""
    from spine.ops.anomalies import list_anomalies as _list
    from spine.ops.requests import ListAnomaliesRequest

    ctx, _ = make_context(database)
    request = ListAnomaliesRequest(
        workflow=workflow, severity=severity, limit=limit, offset=offset,
    )
    result = _list(ctx, request)
    output_paged(result, as_json=json_out, title="Anomalies")
