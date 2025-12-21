"""
CLI: ``spine-core alerts`` — alert channel and delivery management.
"""

from __future__ import annotations

import json

import typer

from spine.cli.utils import console, err_console, make_context, output_paged, output_result

app = typer.Typer(no_args_is_help=True)


# ------------------------------------------------------------------ #
# Alert Channels Commands
# ------------------------------------------------------------------ #


@app.command("channels")
def list_channels(
    channel_type: str | None = typer.Option(None, "--type", "-t"),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List configured alert channels."""
    from spine.ops.alerts import list_alert_channels as _list
    from spine.ops.requests import ListAlertChannelsRequest

    ctx, _ = make_context(database)
    request = ListAlertChannelsRequest(
        channel_type=channel_type,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)
    output_paged(result, as_json=json_out, title="Alert Channels")


@app.command("channel-create")
def create_channel(
    name: str = typer.Argument(..., help="Unique channel name"),
    channel_type: str = typer.Option("slack", "--type", "-t", help="Channel type: slack, email, webhook"),
    config: str = typer.Option("{}", "--config", "-c", help="JSON configuration"),
    min_severity: str = typer.Option("ERROR", "--severity", "-s", help="Minimum severity"),
    throttle: int = typer.Option(5, "--throttle", help="Throttle minutes"),
    disabled: bool = typer.Option(False, "--disabled", help="Create disabled"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Create a new alert channel."""
    from spine.ops.alerts import create_alert_channel as _create
    from spine.ops.requests import CreateAlertChannelRequest

    try:
        config_dict = json.loads(config)
    except json.JSONDecodeError as e:
        err_console.print(f"[bold red]Invalid JSON config:[/bold red] {e}")
        raise typer.Exit(code=1) from e

    ctx, _ = make_context(database)
    request = CreateAlertChannelRequest(
        name=name,
        channel_type=channel_type,
        config=config_dict,
        min_severity=min_severity,
        throttle_minutes=throttle,
        enabled=not disabled,
    )
    result = _create(ctx, request)
    output_result(result, as_json=json_out, title="Created Channel")


@app.command("channel-get")
def get_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Get alert channel details."""
    from spine.ops.alerts import get_alert_channel as _get

    ctx, _ = make_context(database)
    result = _get(ctx, channel_id)
    output_result(result, as_json=json_out, title="Channel Details")


@app.command("channel-delete")
def delete_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    database: str | None = typer.Option(None, "--database", "-d"),
) -> None:
    """Delete an alert channel."""
    from spine.ops.alerts import delete_alert_channel as _delete

    if not force:
        if not typer.confirm(f"Delete channel {channel_id}?"):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(code=0)

    ctx, _ = make_context(database)
    result = _delete(ctx, channel_id)
    if result.success:
        console.print(f"[green]✓[/green] Deleted channel {channel_id}")
    else:
        err_console.print(f"[bold red]Error:[/bold red] {result.error.message if result.error else 'Unknown error'}")
        raise typer.Exit(code=1)


@app.command("channel-enable")
def enable_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
) -> None:
    """Enable an alert channel."""
    from spine.ops.alerts import update_alert_channel as _update

    ctx, _ = make_context(database)
    result = _update(ctx, channel_id, enabled=True)
    if result.success:
        console.print(f"[green]✓[/green] Enabled channel {channel_id}")
    else:
        err_console.print(f"[bold red]Error:[/bold red] {result.error.message if result.error else 'Unknown error'}")
        raise typer.Exit(code=1)


@app.command("channel-disable")
def disable_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
) -> None:
    """Disable an alert channel."""
    from spine.ops.alerts import update_alert_channel as _update

    ctx, _ = make_context(database)
    result = _update(ctx, channel_id, enabled=False)
    if result.success:
        console.print(f"[yellow]⏸[/yellow] Disabled channel {channel_id}")
    else:
        err_console.print(f"[bold red]Error:[/bold red] {result.error.message if result.error else 'Unknown error'}")
        raise typer.Exit(code=1)


# ------------------------------------------------------------------ #
# Alerts Commands
# ------------------------------------------------------------------ #


@app.command("list")
def list_alerts(
    severity: str | None = typer.Option(None, "--severity", "-s"),
    source: str | None = typer.Option(None, "--source"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List alerts."""
    from spine.ops.alerts import list_alerts as _list
    from spine.ops.requests import ListAlertsRequest

    ctx, _ = make_context(database)
    request = ListAlertsRequest(
        severity=severity,
        source=source,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)
    output_paged(result, as_json=json_out, title="Alerts")


@app.command("ack")
def acknowledge_alert(
    alert_id: str = typer.Argument(..., help="Alert ID"),
    database: str | None = typer.Option(None, "--database", "-d"),
) -> None:
    """Acknowledge an alert."""
    from spine.ops.alerts import acknowledge_alert as _ack

    ctx, _ = make_context(database)
    result = _ack(ctx, alert_id)
    if result.success:
        console.print(f"[green]✓[/green] Acknowledged alert {alert_id}")
    else:
        err_console.print(f"[bold red]Error:[/bold red] {result.error.message if result.error else 'Unknown error'}")
        raise typer.Exit(code=1)


# ------------------------------------------------------------------ #
# Alert Deliveries Commands
# ------------------------------------------------------------------ #


@app.command("deliveries")
def list_deliveries(
    alert_id: str | None = typer.Option(None, "--alert"),
    channel_id: str | None = typer.Option(None, "--channel"),
    status: str | None = typer.Option(None, "--status"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    database: str | None = typer.Option(None, "--database", "-d"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List alert delivery attempts."""
    from spine.ops.alerts import list_alert_deliveries as _list
    from spine.ops.requests import ListAlertDeliveriesRequest

    ctx, _ = make_context(database)
    request = ListAlertDeliveriesRequest(
        alert_id=alert_id,
        channel_id=channel_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)
    output_paged(result, as_json=json_out, title="Alert Deliveries")
