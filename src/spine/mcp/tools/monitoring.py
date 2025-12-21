"""Quality, anomaly, and alert monitoring MCP tools."""

from __future__ import annotations

from typing import Any

from spine.mcp import _app

mcp = _app.mcp


@mcp.tool()
async def list_quality_results(
    workflow: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List quality check results.

    Args:
        workflow: Filter by workflow name
        limit: Maximum results to return

    Returns:
        Dictionary with quality results
    """
    from spine.ops.context import OperationContext
    from spine.ops.quality import list_quality_results as _list_quality_results
    from spine.ops.requests import ListQualityResultsRequest

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "results": []}

    request = ListQualityResultsRequest(workflow=workflow, limit=limit)
    result = _list_quality_results(OperationContext(conn=ctx.conn), request)

    return {
        "results": [
            {
                "workflow": qr.workflow,
                "checks_passed": qr.checks_passed,
                "checks_failed": qr.checks_failed,
                "score": qr.score,
                "run_at": qr.run_at.isoformat() if qr.run_at else None,
            }
            for qr in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def list_anomalies(
    workflow: str | None = None,
    severity: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List detected anomalies.

    Args:
        workflow: Filter by workflow name
        severity: Filter by severity (LOW, MEDIUM, HIGH, CRITICAL)
        limit: Maximum anomalies to return

    Returns:
        Dictionary with anomalies list
    """
    from spine.ops.anomalies import list_anomalies as _list_anomalies
    from spine.ops.context import OperationContext
    from spine.ops.requests import ListAnomaliesRequest

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "anomalies": []}

    request = ListAnomaliesRequest(workflow=workflow, severity=severity, limit=limit)
    result = _list_anomalies(OperationContext(conn=ctx.conn), request)

    return {
        "anomalies": [
            {
                "id": a.id,
                "workflow": a.workflow,
                "metric": a.metric,
                "severity": a.severity,
                "value": a.value,
                "threshold": a.threshold,
                "detected_at": a.detected_at.isoformat() if a.detected_at else None,
            }
            for a in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def list_alerts(
    severity: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List system alerts.

    Args:
        severity: Filter by severity (ERROR, WARN, INFO)
        limit: Maximum alerts to return

    Returns:
        Dictionary with alerts list
    """
    from spine.ops.alerts import list_alerts as _list_alerts
    from spine.ops.context import OperationContext
    from spine.ops.requests import ListAlertsRequest

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "alerts": []}

    request = ListAlertsRequest(severity=severity, limit=limit)
    result = _list_alerts(OperationContext(conn=ctx.conn), request)

    return {
        "alerts": [
            {
                "id": a.id,
                "severity": a.severity,
                "title": a.title,
                "message": a.message,
                "source": a.source,
                "created_at": str(a.created_at) if a.created_at else None,
            }
            for a in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def list_alert_channels(
    channel_type: str | None = None,
    enabled: bool | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List configured alert channels.

    Args:
        channel_type: Filter by type (slack, email, webhook, pagerduty)
        enabled: Filter by enabled status
        limit: Maximum channels to return

    Returns:
        Dictionary with 'channels' list and 'total' count
    """
    from spine.ops.alerts import list_alert_channels as _list_alert_channels
    from spine.ops.context import OperationContext
    from spine.ops.requests import ListAlertChannelsRequest

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized", "channels": [], "total": 0}

    request = ListAlertChannelsRequest(
        channel_type=channel_type,
        enabled=enabled,
        limit=limit,
    )
    result = _list_alert_channels(OperationContext(conn=ctx.conn), request)

    return {
        "channels": [
            {
                "id": ch.id,
                "name": ch.name,
                "channel_type": ch.channel_type,
                "min_severity": ch.min_severity,
                "enabled": ch.enabled,
                "consecutive_failures": ch.consecutive_failures,
            }
            for ch in result.items
        ],
        "total": result.total,
    }


@mcp.tool()
async def create_alert_channel(
    name: str,
    channel_type: str = "slack",
    config: dict[str, Any] | None = None,
    min_severity: str = "ERROR",
    enabled: bool = True,
    throttle_minutes: int = 5,
) -> dict[str, Any]:
    """Create a new alert channel for notifications.

    Args:
        name: Channel name
        channel_type: Notification type (slack, email, webhook, pagerduty)
        config: Channel-specific configuration (e.g., webhook URL)
        min_severity: Minimum severity to trigger (ERROR, WARN, INFO)
        enabled: Whether channel is active
        throttle_minutes: Minimum minutes between repeated alerts

    Returns:
        Dictionary with channel_id
    """
    from spine.ops.alerts import create_alert_channel as _create_alert_channel
    from spine.ops.context import OperationContext
    from spine.ops.requests import CreateAlertChannelRequest

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    request = CreateAlertChannelRequest(
        name=name,
        channel_type=channel_type,
        config=config or {},
        min_severity=min_severity,
        enabled=enabled,
        throttle_minutes=throttle_minutes,
    )
    result = _create_alert_channel(OperationContext(conn=ctx.conn), request)

    if not result.success:
        return {"error": result.error_message}

    return result.data


@mcp.tool()
async def acknowledge_alert(
    alert_id: str,
    acknowledged_by: str | None = None,
) -> dict[str, Any]:
    """Acknowledge an alert (mark as reviewed).

    Updates the alert metadata to record who acknowledged it and when.

    Args:
        alert_id: Unique alert identifier
        acknowledged_by: Name or ID of the person acknowledging

    Returns:
        Confirmation of acknowledgement
    """
    from spine.ops.alerts import acknowledge_alert as _acknowledge_alert
    from spine.ops.context import OperationContext

    ctx = _app._get_context()
    if not ctx.initialized:
        return {"error": "Database not initialized"}

    result = _acknowledge_alert(
        OperationContext(conn=ctx.conn),
        alert_id,
        acknowledged_by=acknowledged_by,
    )

    if not result.success:
        return {"error": result.error_message}

    return result.data
