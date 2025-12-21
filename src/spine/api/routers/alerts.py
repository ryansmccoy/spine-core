"""
Alerts router — alert channel configuration and delivery tracking.

Provides endpoints for managing alert channels, viewing alerts,
and tracking delivery status.

Endpoints:
    GET  /alerts/channels         List configured alert channels
    POST /alerts/channels         Create a new alert channel
    GET  /alerts/channels/{id}    Get alert channel details
    DELETE /alerts/channels/{id}  Delete an alert channel
    PATCH /alerts/channels/{id}   Update an alert channel
    GET  /alerts                  List alerts
    POST /alerts                  Create a new alert
    POST /alerts/{id}/ack         Acknowledge an alert
    GET  /alerts/deliveries       List alert deliveries

Manifesto:
    Alert channels must be configurable at runtime so operators
    can add Slack, email, or PagerDuty targets without redeploying.

Tags:
    spine-core, api, alerts, channels, delivery, notifications

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field

from spine.api.deps import OpContext
from spine.api.schemas.common import PagedResponse, PageMeta
from spine.api.utils import _dc, _handle_error

router = APIRouter(prefix="/alerts")


# ------------------------------------------------------------------ #
# Pydantic Schemas
# ------------------------------------------------------------------ #


class AlertChannelSchema(BaseModel):
    """Alert channel representation."""

    id: str
    name: str
    channel_type: str
    min_severity: str = "ERROR"
    enabled: bool = True
    consecutive_failures: int = 0
    created_at: str | None = None


class AlertChannelDetailSchema(BaseModel):
    """Full alert channel representation."""

    id: str
    name: str
    channel_type: str
    config: dict[str, Any] = {}
    min_severity: str = "ERROR"
    domains: list[str] | None = None
    enabled: bool = True
    throttle_minutes: int = 5
    last_success_at: str | None = None
    last_failure_at: str | None = None
    consecutive_failures: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class AlertChannelCreateRequest(BaseModel):
    """Request body for creating an alert channel."""

    name: str = Field(..., description="Unique channel name")
    channel_type: str = Field(..., description="Channel type: slack, email, webhook, servicenow, pagerduty")
    config: dict[str, Any] = Field(default_factory=dict, description="Type-specific configuration")
    min_severity: str = Field(default="ERROR", description="Minimum severity: INFO, WARNING, ERROR, CRITICAL")
    domains: list[str] | None = Field(default=None, description="Domain filters (null = all)")
    enabled: bool = Field(default=True, description="Whether channel is active")
    throttle_minutes: int = Field(default=5, description="Minutes between duplicate alerts")


class AlertChannelUpdateRequest(BaseModel):
    """Request body for updating an alert channel."""

    enabled: bool | None = None
    min_severity: str | None = None
    throttle_minutes: int | None = None


class AlertSchema(BaseModel):
    """Alert representation."""

    id: str
    severity: str
    title: str
    message: str
    source: str
    domain: str | None = None
    created_at: str | None = None


class AlertCreateRequest(BaseModel):
    """Request body for creating an alert."""

    severity: str = Field(default="ERROR", description="Alert severity")
    title: str = Field(..., description="Alert title")
    message: str = Field(..., description="Alert message")
    source: str = Field(..., description="Source system/workflow")
    domain: str | None = Field(default=None, description="Domain context")
    execution_id: str | None = Field(default=None, description="Related execution ID")
    run_id: str | None = Field(default=None, description="Related workflow run ID")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional context")
    error_category: str | None = Field(default=None, description="Error classification")


class AlertDeliverySchema(BaseModel):
    """Alert delivery representation."""

    id: str
    alert_id: str
    channel_id: str
    channel_name: str
    status: str
    attempted_at: str | None = None
    delivered_at: str | None = None
    error: str | None = None
    attempt: int = 1


# ------------------------------------------------------------------ #
# Alert Channels Endpoints
# ------------------------------------------------------------------ #


@router.get("/channels", response_model=PagedResponse[AlertChannelSchema])
def list_alert_channels(
    ctx: OpContext,
    channel_type: str | None = Query(None, description="Filter by channel type"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List configured alert channels.

    Returns alert channels for sending notifications. Channels can be
    filtered by type (slack, email, webhook) and enabled status.
    """
    from spine.ops.alerts import list_alert_channels as _list
    from spine.ops.requests import ListAlertChannelsRequest

    request = ListAlertChannelsRequest(
        channel_type=channel_type,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)

    if not result.success:
        return _handle_error(result)

    items = [_dc(s) for s in (result.data or [])]
    return {
        "data": items,
        "meta": PageMeta(
            total=result.total,
            limit=result.limit,
            offset=result.offset,
            has_more=result.has_more,
        ).model_dump(),
    }


@router.post("/channels", status_code=201)
def create_alert_channel(
    ctx: OpContext,
    body: AlertChannelCreateRequest,
):
    """Create a new alert channel.

    Registers a new notification channel for alert delivery.
    The channel will start receiving alerts matching its severity threshold.
    """
    from spine.ops.alerts import create_alert_channel as _create
    from spine.ops.requests import CreateAlertChannelRequest

    request = CreateAlertChannelRequest(
        name=body.name,
        channel_type=body.channel_type,
        config=body.config,
        min_severity=body.min_severity,
        domains=body.domains,
        enabled=body.enabled,
        throttle_minutes=body.throttle_minutes,
    )
    result = _create(ctx, request)

    if not result.success:
        return _handle_error(result)

    return result.data


@router.get("/channels/{channel_id}", response_model=AlertChannelDetailSchema)
def get_alert_channel(
    ctx: OpContext,
    channel_id: str = Path(..., description="Alert channel ID"),
):
    """Get alert channel details.

    Returns full configuration and health status for a specific channel.
    """
    from spine.ops.alerts import get_alert_channel as _get

    result = _get(ctx, channel_id)

    if not result.success:
        return _handle_error(result)

    return _dc(result.data)


@router.delete("/channels/{channel_id}")
def delete_alert_channel(
    ctx: OpContext,
    channel_id: str = Path(..., description="Alert channel ID"),
):
    """Delete an alert channel.

    Removes the channel. Pending deliveries will fail.
    """
    from spine.ops.alerts import delete_alert_channel as _delete

    result = _delete(ctx, channel_id)

    if not result.success:
        return _handle_error(result)

    return result.data


@router.patch("/channels/{channel_id}")
def update_alert_channel(
    ctx: OpContext,
    body: AlertChannelUpdateRequest,
    channel_id: str = Path(..., description="Alert channel ID"),
):
    """Update an alert channel.

    Modify channel settings like enabled status or severity threshold.
    """
    from spine.ops.alerts import update_alert_channel as _update

    result = _update(
        ctx,
        channel_id,
        enabled=body.enabled,
        min_severity=body.min_severity,
        throttle_minutes=body.throttle_minutes,
    )

    if not result.success:
        return _handle_error(result)

    return result.data


# ------------------------------------------------------------------ #
# Alerts Endpoints
# ------------------------------------------------------------------ #


@router.get("", response_model=PagedResponse[AlertSchema])
def list_alerts(
    ctx: OpContext,
    severity: str | None = Query(None, description="Filter by severity"),
    source: str | None = Query(None, description="Filter by source"),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List alerts.

    Returns triggered alerts with optional filtering by severity and source.
    """
    from spine.ops.alerts import list_alerts as _list
    from spine.ops.requests import ListAlertsRequest

    request = ListAlertsRequest(
        severity=severity,
        source=source,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)

    if not result.success:
        return _handle_error(result)

    items = [_dc(s) for s in (result.data or [])]
    return {
        "data": items,
        "meta": PageMeta(
            total=result.total,
            limit=result.limit,
            offset=result.offset,
            has_more=result.has_more,
        ).model_dump(),
    }


@router.post("", status_code=201)
def create_alert(
    ctx: OpContext,
    body: AlertCreateRequest,
):
    """Create a new alert.

    Triggers a new alert that will be routed to matching channels.
    """
    from spine.ops.alerts import create_alert as _create
    from spine.ops.requests import CreateAlertRequest

    request = CreateAlertRequest(
        severity=body.severity,
        title=body.title,
        message=body.message,
        source=body.source,
        domain=body.domain,
        execution_id=body.execution_id,
        run_id=body.run_id,
        metadata=body.metadata,
        error_category=body.error_category,
    )
    result = _create(ctx, request)

    if not result.success:
        return _handle_error(result)

    return result.data


@router.post("/{alert_id}/ack")
def acknowledge_alert(
    ctx: OpContext,
    alert_id: str = Path(..., description="Alert ID"),
):
    """Acknowledge an alert.

    Mark the alert as reviewed. This updates the alert's metadata.
    """
    from spine.ops.alerts import acknowledge_alert as _ack

    result = _ack(ctx, alert_id)

    if not result.success:
        return _handle_error(result)

    return result.data


# ------------------------------------------------------------------ #
# Alert Deliveries Endpoints
# ------------------------------------------------------------------ #


@router.get("/deliveries", response_model=PagedResponse[AlertDeliverySchema])
def list_alert_deliveries(
    ctx: OpContext,
    alert_id: str | None = Query(None, description="Filter by alert ID"),
    channel_id: str | None = Query(None, description="Filter by channel ID"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List alert delivery attempts.

    Returns delivery attempts for alerts to channels with status tracking.
    """
    from spine.ops.alerts import list_alert_deliveries as _list
    from spine.ops.requests import ListAlertDeliveriesRequest

    request = ListAlertDeliveriesRequest(
        alert_id=alert_id,
        channel_id=channel_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    result = _list(ctx, request)

    if not result.success:
        return _handle_error(result)

    items = [_dc(s) for s in (result.data or [])]
    return {
        "data": items,
        "meta": PageMeta(
            total=result.total,
            limit=result.limit,
            offset=result.offset,
            has_more=result.has_more,
        ).model_dump(),
    }
