"""Alert management endpoints.

Provides API access to alerts and alert channels.

Follows API Design Guardrails:
- Resource-style URLs: /v1/alerts, /v1/alerts/channels
- Pagination: offset/limit with has_more
- Standard error envelope
"""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================


class PaginationMeta(BaseModel):
    """Standard pagination metadata."""
    offset: int
    limit: int
    total: int
    has_more: bool


# -----------------------------------------------------------------------------
# Alert Channels
# -----------------------------------------------------------------------------


class ChannelConfigSlack(BaseModel):
    """Slack channel configuration."""
    webhook_url: str = Field(..., description="Slack webhook URL")
    channel: str | None = Field(None, description="Override channel")
    username: str = Field("Spine Alerts", description="Bot username")


class ChannelConfigEmail(BaseModel):
    """Email channel configuration."""
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password_ref: str | None = Field(None, description="Reference to secret store")
    from_address: str
    recipients: list[str]
    use_tls: bool = True


class ChannelConfigServiceNow(BaseModel):
    """ServiceNow channel configuration."""
    instance: str = Field(..., description="ServiceNow instance (e.g., 'company.service-now.com')")
    username: str
    password_ref: str = Field(..., description="Reference to secret store")
    assignment_group: str


class AlertChannelCreate(BaseModel):
    """Request to create an alert channel."""
    name: str = Field(..., description="Unique channel name")
    channel_type: Literal["slack", "email", "servicenow", "webhook"] = Field(..., description="Channel type")
    config: dict[str, Any] = Field(..., description="Type-specific configuration")
    min_severity: Literal["INFO", "WARNING", "ERROR", "CRITICAL"] = Field("ERROR", description="Minimum alert severity")
    domains: list[str] | None = Field(None, description="Domain filters (e.g., ['finra.*'])")
    enabled: bool = Field(True, description="Whether channel is active")
    throttle_minutes: int = Field(5, description="Min interval between same alerts")


class AlertChannelUpdate(BaseModel):
    """Request to update an alert channel."""
    config: dict[str, Any] | None = None
    min_severity: Literal["INFO", "WARNING", "ERROR", "CRITICAL"] | None = None
    domains: list[str] | None = None
    enabled: bool | None = None
    throttle_minutes: int | None = None


class AlertChannelResponse(BaseModel):
    """Alert channel details."""
    id: str
    name: str
    channel_type: str
    config: dict[str, Any]  # Sensitive fields redacted
    min_severity: str
    domains: list[str] | None
    enabled: bool
    throttle_minutes: int
    
    # Health
    last_success_at: datetime | None
    last_failure_at: datetime | None
    consecutive_failures: int
    
    # Audit
    created_at: datetime
    updated_at: datetime
    created_by: str | None

    model_config = {"from_attributes": True}


class AlertChannelList(BaseModel):
    """Paginated list of alert channels."""
    data: list[AlertChannelResponse]
    pagination: PaginationMeta


# -----------------------------------------------------------------------------
# Alerts
# -----------------------------------------------------------------------------


class AlertSummary(BaseModel):
    """Summary of an alert for list views."""
    id: str
    severity: Literal["INFO", "WARNING", "ERROR", "CRITICAL"]
    title: str
    source: str
    domain: str | None
    created_at: datetime
    
    # Delivery summary
    delivery_count: int
    success_count: int
    failed_count: int

    model_config = {"from_attributes": True}


class AlertDeliveryDetail(BaseModel):
    """Alert delivery details."""
    id: str
    channel_id: str
    channel_name: str
    status: Literal["PENDING", "SENT", "FAILED", "THROTTLED"]
    attempted_at: datetime | None
    delivered_at: datetime | None
    error: str | None
    attempt: int

    model_config = {"from_attributes": True}


class AlertDetail(BaseModel):
    """Full alert details with deliveries."""
    id: str
    severity: Literal["INFO", "WARNING", "ERROR", "CRITICAL"]
    title: str
    message: str
    source: str
    domain: str | None
    execution_id: str | None
    run_id: str | None
    metadata: dict[str, Any] | None
    error_category: str | None
    created_at: datetime
    capture_id: str | None
    
    # Deliveries
    deliveries: list[AlertDeliveryDetail] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AlertList(BaseModel):
    """Paginated list of alerts."""
    data: list[AlertSummary]
    pagination: PaginationMeta


class AlertCreate(BaseModel):
    """Request to create an alert (for testing/manual alerts)."""
    severity: Literal["INFO", "WARNING", "ERROR", "CRITICAL"]
    title: str
    message: str
    source: str
    domain: str | None = None
    metadata: dict[str, Any] | None = None


class AlertActionResponse(BaseModel):
    """Response for alert actions."""
    id: str
    status: str
    message: str


class ChannelTestResponse(BaseModel):
    """Response for channel test."""
    channel_id: str
    channel_name: str
    success: bool
    message: str
    response: dict[str, Any] | None = None


# =============================================================================
# ALERT CHANNEL ENDPOINTS
# =============================================================================


@router.get(
    "/channels",
    response_model=AlertChannelList,
    summary="List alert channels",
    description="Get configured alert channels",
)
async def list_channels(
    channel_type: str | None = Query(None, description="Filter by channel type"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """List all configured alert channels."""
    # TODO: Implement with AlertChannelRepository
    return AlertChannelList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )


@router.post(
    "/channels",
    response_model=AlertChannelResponse,
    status_code=201,
    summary="Create alert channel",
    description="Configure a new alert channel",
)
async def create_channel(request: AlertChannelCreate):
    """
    Create a new alert channel.
    
    The channel will start receiving alerts immediately if enabled.
    """
    # TODO: Implement
    raise HTTPException(
        status_code=501,
        detail={"code": "NOT_IMPLEMENTED", "message": "Channel creation not yet implemented"},
    )


@router.get(
    "/channels/{channel_id}",
    response_model=AlertChannelResponse,
    summary="Get alert channel",
    description="Get channel details",
)
async def get_channel(
    channel_id: str = Path(..., description="Channel ID"),
):
    """Get details of a specific channel."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Channel not found: {channel_id}"},
    )


@router.patch(
    "/channels/{channel_id}",
    response_model=AlertChannelResponse,
    summary="Update alert channel",
    description="Update channel configuration",
)
async def update_channel(
    channel_id: str = Path(..., description="Channel ID"),
    request: AlertChannelUpdate = ...,
):
    """Update an existing alert channel."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Channel not found: {channel_id}"},
    )


@router.delete(
    "/channels/{channel_id}",
    status_code=204,
    summary="Delete alert channel",
    description="Remove an alert channel",
)
async def delete_channel(
    channel_id: str = Path(..., description="Channel ID"),
):
    """Delete an alert channel."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Channel not found: {channel_id}"},
    )


@router.post(
    "/channels/{channel_id}/test",
    response_model=ChannelTestResponse,
    summary="Test alert channel",
    description="Send a test alert to verify channel configuration",
)
async def test_channel(
    channel_id: str = Path(..., description="Channel ID"),
):
    """
    Send a test alert to verify channel configuration.
    
    Returns the result of the test delivery.
    """
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Channel not found: {channel_id}"},
    )


@router.post(
    "/channels/{channel_id}/enable",
    response_model=AlertActionResponse,
    summary="Enable channel",
)
async def enable_channel(channel_id: str = Path(...)):
    """Enable a disabled channel."""
    raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"Channel not found: {channel_id}"})


@router.post(
    "/channels/{channel_id}/disable",
    response_model=AlertActionResponse,
    summary="Disable channel",
)
async def disable_channel(channel_id: str = Path(...)):
    """Disable a channel."""
    raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"Channel not found: {channel_id}"})


# =============================================================================
# ALERT ENDPOINTS
# =============================================================================


@router.get(
    "",
    response_model=AlertList,
    summary="List alerts",
    description="Get paginated list of alerts",
)
async def list_alerts(
    severity: str | None = Query(None, description="Filter by severity"),
    source: str | None = Query(None, description="Filter by source"),
    domain: str | None = Query(None, description="Filter by domain"),
    start_date: str | None = Query(None, description="Filter by date range start"),
    end_date: str | None = Query(None, description="Filter by date range end"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """
    List alerts with optional filtering.
    
    Returns summary information. Use GET /alerts/{id} for full details.
    """
    return AlertList(
        data=[],
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=0,
            has_more=False,
        ),
    )


@router.get(
    "/{alert_id}",
    response_model=AlertDetail,
    summary="Get alert details",
    description="Get full alert details including delivery status",
)
async def get_alert(
    alert_id: str = Path(..., description="Alert ID"),
):
    """Get full details of an alert including all delivery attempts."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Alert not found: {alert_id}"},
    )


@router.post(
    "",
    response_model=AlertDetail,
    status_code=201,
    summary="Create alert",
    description="Create and send a manual alert",
)
async def create_alert(request: AlertCreate):
    """
    Create and send a manual alert.
    
    This is useful for testing or external integrations.
    """
    raise HTTPException(
        status_code=501,
        detail={"code": "NOT_IMPLEMENTED", "message": "Alert creation not yet implemented"},
    )


@router.post(
    "/{alert_id}/retry",
    response_model=AlertActionResponse,
    summary="Retry failed deliveries",
    description="Retry failed delivery attempts for an alert",
)
async def retry_alert_deliveries(
    alert_id: str = Path(..., description="Alert ID"),
    channel_id: str | None = Query(None, description="Specific channel to retry"),
):
    """Retry failed deliveries for an alert."""
    raise HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Alert not found: {alert_id}"},
    )


# =============================================================================
# ALERT STATISTICS
# =============================================================================


class AlertStats(BaseModel):
    """Alert statistics."""
    period: str  # e.g., "24h", "7d", "30d"
    total_alerts: int
    by_severity: dict[str, int]
    by_source: dict[str, int]
    by_domain: dict[str, int]
    delivery_success_rate: float
    avg_delivery_time_ms: float | None


@router.get(
    "/stats",
    response_model=AlertStats,
    summary="Get alert statistics",
    description="Get aggregate statistics about alerts",
)
async def get_alert_stats(
    period: str = Query("24h", description="Time period: 1h, 24h, 7d, 30d"),
):
    """Get aggregate statistics about alerts."""
    return AlertStats(
        period=period,
        total_alerts=0,
        by_severity={},
        by_source={},
        by_domain={},
        delivery_success_rate=0.0,
        avg_delivery_time_ms=None,
    )
