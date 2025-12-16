"""Alerting table models (04_alerting.sql).

Models for alert channel configuration and delivery tracking:
channels, alerts, delivery logs, and throttle state.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# core_alert_channels
# ---------------------------------------------------------------------------


@dataclass
class AlertChannel:
    """Alert channel configuration row (``core_alert_channels``)."""

    id: str = ""
    name: str = ""
    channel_type: str = ""  # slack, email, servicenow, pagerduty, webhook
    config_json: str = ""  # JSON type-specific configuration
    min_severity: str = "ERROR"  # INFO, WARNING, ERROR, CRITICAL
    domains: str | None = None  # JSON array of domain patterns
    enabled: int = 1
    throttle_minutes: int = 5
    last_success_at: str | None = None
    last_failure_at: str | None = None
    consecutive_failures: int = 0
    created_at: str = ""
    updated_at: str = ""
    created_by: str | None = None


# ---------------------------------------------------------------------------
# core_alerts
# ---------------------------------------------------------------------------


@dataclass
class Alert:
    """Alert record row (``core_alerts``)."""

    id: str = ""
    severity: str = ""  # INFO, WARNING, ERROR, CRITICAL
    title: str = ""
    message: str = ""
    source: str = ""
    domain: str | None = None
    execution_id: str | None = None
    run_id: str | None = None
    metadata_json: str | None = None  # JSON additional context
    error_category: str | None = None
    created_at: str = ""
    dedup_key: str | None = None
    capture_id: str | None = None


# ---------------------------------------------------------------------------
# core_alert_deliveries
# ---------------------------------------------------------------------------


@dataclass
class AlertDelivery:
    """Delivery status per channel (``core_alert_deliveries``)."""

    id: str = ""
    alert_id: str = ""
    channel_id: str = ""
    channel_name: str = ""
    status: str = "PENDING"  # PENDING, SENT, FAILED, THROTTLED
    attempted_at: str | None = None
    delivered_at: str | None = None
    response_json: str | None = None  # JSON channel response
    error: str | None = None
    attempt: int = 1
    next_retry_at: str | None = None
    created_at: str = ""


# ---------------------------------------------------------------------------
# core_alert_throttle
# ---------------------------------------------------------------------------


@dataclass
class AlertThrottle:
    """Alert deduplication / throttle state (``core_alert_throttle``)."""

    dedup_key: str = ""
    last_sent_at: str = ""
    send_count: int = 1
    expires_at: str = ""
