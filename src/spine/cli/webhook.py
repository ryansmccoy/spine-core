"""CLI commands for webhook management.

Usage::

    spine-core webhook list
    spine-core webhook register sec.daily_ingest --kind workflow
    spine-core webhook register finra.download --kind pipeline --description "Download FINRA data"
"""

from __future__ import annotations

import sys

try:
    import typer
except ImportError:  # pragma: no cover
    print("typer is required for the CLI.  Install with:  pip install spine-core[cli]")
    sys.exit(1)

app = typer.Typer(
    name="webhook",
    help="Manage webhook triggers.",
    no_args_is_help=True,
)


@app.command("list")
def list_webhooks() -> None:
    """List all registered webhook targets."""
    from spine.ops.webhooks import list_registered_webhooks

    targets = list_registered_webhooks()
    if not targets:
        typer.echo("No webhook targets registered.")
        return

    typer.echo(f"{'KIND':<12} {'NAME':<40} {'DESCRIPTION'}")
    typer.echo("-" * 72)
    for t in targets:
        typer.echo(f"{t.kind:<12} {t.name:<40} {t.description}")


@app.command("register")
def register(
    name: str = typer.Argument(..., help="Workflow or pipeline name"),
    kind: str = typer.Option("workflow", "--kind", "-k", help="Type: workflow or pipeline"),
    description: str = typer.Option("", "--description", "-d", help="Human-readable description"),
) -> None:
    """Register a workflow or pipeline as a webhook target."""
    from spine.ops.webhooks import register_webhook

    register_webhook(name, kind=kind, description=description)
    typer.echo(f"Registered webhook: {kind}:{name}")
