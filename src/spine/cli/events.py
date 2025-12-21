"""
CLI: ``spine-core events`` — event bus management and diagnostics.
"""

from __future__ import annotations

import asyncio
import json

import typer

from spine.cli.utils import console, err_console

app = typer.Typer(no_args_is_help=True)


@app.command("status")
def status(
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show event bus status (backend, subscriptions)."""
    from spine.core.events import get_event_bus

    bus = get_event_bus()
    backend = type(bus).__name__
    sub_count = getattr(bus, "subscription_count", 0)
    closed = getattr(bus, "_closed", False)

    info = {
        "backend": backend,
        "subscription_count": sub_count,
        "closed": closed,
    }

    if json_out:
        console.print_json(json.dumps(info))
    else:
        console.print("[bold]Event Bus[/bold]")
        console.print(f"  Backend:       {backend}")
        console.print(f"  Subscriptions: {sub_count}")
        console.print(f"  Closed:        {closed}")


@app.command("publish")
def publish(
    event_type: str = typer.Argument(..., help="Dot-separated event type (e.g. run.started)"),
    source: str = typer.Option("cli", "--source", "-s", help="Event source"),
    payload: str = typer.Option("{}", "--payload", "-p", help="JSON payload"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Publish a test event to the bus."""
    from spine.core.events import Event, get_event_bus

    try:
        payload_dict = json.loads(payload)
    except json.JSONDecodeError as e:
        err_console.print(f"[bold red]Invalid JSON payload:[/bold red] {e}")
        raise typer.Exit(code=1) from e

    event = Event(
        event_type=event_type,
        source=source,
        payload=payload_dict,
    )

    bus = get_event_bus()
    asyncio.run(bus.publish(event))

    info = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "published": True,
    }

    if json_out:
        console.print_json(json.dumps(info))
    else:
        console.print(f"[green]Published[/green] {event.event_type} (id={event.event_id})")
