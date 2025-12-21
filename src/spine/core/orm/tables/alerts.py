"""Alerting table definitions — channels, alerts, deliveries, throttles.

Tags:
    spine-core, orm, sqlalchemy, tables, alerting

Doc-Types:
    api-reference, data-model
"""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spine.core.orm.base import SpineBase

_NOW = text("(datetime('now'))")


class AlertChannelTable(SpineBase):
    __tablename__ = "core_alert_channels"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    channel_type: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    min_severity: Mapped[str] = mapped_column(
        Text, default="ERROR", nullable=False
    )
    domains: Mapped[list | None] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Integer, default=True, nullable=False)
    throttle_minutes: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False
    )
    last_success_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    last_failure_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    created_by: Mapped[str | None] = mapped_column(Text)


class AlertTable(SpineBase):
    __tablename__ = "core_alerts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text)
    execution_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_executions.id")
    )
    run_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("core_workflow_runs.run_id")
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    error_category: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )
    dedup_key: Mapped[str | None] = mapped_column(Text)
    capture_id: Mapped[str | None] = mapped_column(Text)

    # --- relationships ---
    deliveries: Mapped[list[AlertDeliveryTable]] = relationship(
        "AlertDeliveryTable", backref="alert"
    )


class AlertDeliveryTable(SpineBase):
    __tablename__ = "core_alert_deliveries"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    alert_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_alerts.id"), nullable=False
    )
    channel_id: Mapped[str] = mapped_column(
        Text, ForeignKey("core_alert_channels.id"), nullable=False
    )
    channel_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="PENDING", nullable=False)
    attempted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    response_json: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_retry_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=_NOW
    )


class AlertThrottleTable(SpineBase):
    __tablename__ = "core_alert_throttle"

    dedup_key: Mapped[str] = mapped_column(Text, primary_key=True)
    last_sent_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    send_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
