"""
Alert operations.

CRUD for alert channels, alerts, and delivery tracking.
Wires ``core_alert_channels``, ``core_alerts``, ``core_alert_deliveries``,
and ``core_alert_throttle`` tables to the API/CLI.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from spine.core.logging import get_logger
from spine.core.repositories import AlertRepository
from spine.ops.context import OperationContext
from spine.ops.requests import (
    CreateAlertChannelRequest,
    CreateAlertRequest,
    ListAlertChannelsRequest,
    ListAlertDeliveriesRequest,
    ListAlertsRequest,
)
from spine.ops.responses import (
    AlertChannelDetail,
    AlertChannelSummary,
    AlertDeliverySummary,
    AlertSummary,
)
from spine.ops.result import OperationResult, PagedResult, start_timer

logger = get_logger(__name__)


def _alert_repo(ctx: OperationContext) -> AlertRepository:
    return AlertRepository(ctx.conn)


# ------------------------------------------------------------------ #
# Alert Channels
# ------------------------------------------------------------------ #


def list_alert_channels(
    ctx: OperationContext,
    request: ListAlertChannelsRequest,
) -> PagedResult[AlertChannelSummary]:
    """List configured alert channels with optional filtering."""
    timer = start_timer()

    try:
        repo = _alert_repo(ctx)
        rows, total = repo.list_channels(
            channel_type=request.channel_type,
            enabled=request.enabled,
            limit=request.limit,
            offset=request.offset,
        )

        summaries = [_row_to_channel_summary(r) for r in rows]
        return PagedResult.from_items(
            summaries,
            total=total,
            limit=request.limit,
            offset=request.offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to list alert channels: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


def get_alert_channel(
    ctx: OperationContext,
    channel_id: str,
) -> OperationResult[AlertChannelDetail]:
    """Get a single alert channel by ID."""
    timer = start_timer()

    try:
        repo = _alert_repo(ctx)
        row = repo.get_channel(channel_id)

        if not row:
            return OperationResult.fail(
                "NOT_FOUND",
                f"Alert channel '{channel_id}' not found",
                elapsed_ms=timer.elapsed_ms,
            )

        detail = _row_to_channel_detail(row)
        return OperationResult.ok(detail, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to get alert channel: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def create_alert_channel(
    ctx: OperationContext,
    request: CreateAlertChannelRequest,
) -> OperationResult[dict]:
    """Create a new alert channel."""
    timer = start_timer()

    if ctx.dry_run:
        return OperationResult.ok(
            {"dry_run": True, "would_create": request.name},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        import json

        channel_id = f"ch_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()

        repo = _alert_repo(ctx)
        repo.create_channel({
            "id": channel_id,
            "name": request.name,
            "channel_type": request.channel_type,
            "config_json": json.dumps(request.config),
            "min_severity": request.min_severity,
            "domains": json.dumps(request.domains) if request.domains else None,
            "enabled": 1 if request.enabled else 0,
            "throttle_minutes": request.throttle_minutes,
            "created_at": now,
            "updated_at": now,
        })
        ctx.conn.commit()

        return OperationResult.ok(
            {"id": channel_id, "name": request.name, "created": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to create alert channel: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def delete_alert_channel(
    ctx: OperationContext,
    channel_id: str,
    dry_run: bool = False,
) -> OperationResult[dict]:
    """Delete an alert channel."""
    timer = start_timer()

    if dry_run or ctx.dry_run:
        return OperationResult.ok(
            {"dry_run": True, "would_delete": channel_id},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        repo = _alert_repo(ctx)
        repo.delete_channel(channel_id)
        ctx.conn.commit()

        return OperationResult.ok(
            {"id": channel_id, "deleted": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to delete alert channel: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def update_alert_channel(
    ctx: OperationContext,
    channel_id: str,
    *,
    enabled: bool | None = None,
    min_severity: str | None = None,
    throttle_minutes: int | None = None,
) -> OperationResult[dict]:
    """Update an existing alert channel."""
    timer = start_timer()

    updates_dict: dict[str, Any] = {}
    if enabled is not None:
        updates_dict["enabled"] = 1 if enabled else 0
    if min_severity is not None:
        updates_dict["min_severity"] = min_severity
    if throttle_minutes is not None:
        updates_dict["throttle_minutes"] = throttle_minutes

    if not updates_dict:
        return OperationResult.fail(
            "VALIDATION_FAILED",
            "No updates provided",
            elapsed_ms=timer.elapsed_ms,
        )

    updates_dict["updated_at"] = datetime.utcnow().isoformat()

    if ctx.dry_run:
        return OperationResult.ok(
            {"dry_run": True, "would_update": channel_id, "fields": list(updates_dict.keys())},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        repo = _alert_repo(ctx)
        repo.update_channel(channel_id, updates_dict)
        ctx.conn.commit()

        return OperationResult.ok(
            {"id": channel_id, "updated": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to update alert channel: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Alerts
# ------------------------------------------------------------------ #


def list_alerts(
    ctx: OperationContext,
    request: ListAlertsRequest,
) -> PagedResult[AlertSummary]:
    """List alerts with optional filtering."""
    timer = start_timer()

    try:
        repo = _alert_repo(ctx)
        rows, total = repo.list_alerts(
            severity=request.severity,
            source=request.source,
            limit=request.limit,
            offset=request.offset,
        )

        summaries = [_row_to_alert_summary(r) for r in rows]
        return PagedResult.from_items(
            summaries,
            total=total,
            limit=request.limit,
            offset=request.offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to list alerts: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


def create_alert(
    ctx: OperationContext,
    request: CreateAlertRequest,
) -> OperationResult[dict]:
    """Create a new alert and queue for delivery."""
    timer = start_timer()

    if ctx.dry_run:
        return OperationResult.ok(
            {"dry_run": True, "would_create": request.title},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        import hashlib
        import json

        alert_id = f"alert_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()

        # Build dedup key from source + title + severity
        dedup_str = f"{request.source}:{request.title}:{request.severity}"
        dedup_key = hashlib.sha256(dedup_str.encode()).hexdigest()[:32]

        repo = _alert_repo(ctx)
        repo.create_alert({
            "id": alert_id,
            "severity": request.severity,
            "title": request.title,
            "message": request.message,
            "source": request.source,
            "domain": request.domain,
            "execution_id": request.execution_id,
            "run_id": request.run_id,
            "metadata_json": json.dumps(request.metadata) if request.metadata else None,
            "error_category": request.error_category,
            "created_at": now,
            "dedup_key": dedup_key,
        })
        ctx.conn.commit()

        return OperationResult.ok(
            {"id": alert_id, "dedup_key": dedup_key, "created": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to create alert: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def acknowledge_alert(
    ctx: OperationContext,
    alert_id: str,
    *,
    acknowledged_by: str | None = None,
) -> OperationResult[dict]:
    """Acknowledge an alert (mark as reviewed)."""
    timer = start_timer()

    if ctx.dry_run:
        return OperationResult.ok(
            {"dry_run": True, "would_acknowledge": alert_id},
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        import json

        # Update metadata to include acknowledgement
        repo = _alert_repo(ctx)
        alert_row = repo.get_alert(alert_id)
        if alert_row is None:
            return OperationResult.fail(
                "NOT_FOUND",
                f"Alert '{alert_id}' not found",
                elapsed_ms=timer.elapsed_ms,
            )

        raw_meta = alert_row.get("metadata_json") or "{}"
        metadata = json.loads(raw_meta)
        metadata["acknowledged_at"] = datetime.utcnow().isoformat()
        metadata["acknowledged_by"] = acknowledged_by or ctx.user

        repo.update_alert_metadata(alert_id, json.dumps(metadata))
        ctx.conn.commit()

        return OperationResult.ok(
            {"id": alert_id, "acknowledged": True},
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to acknowledge alert: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Alert Deliveries
# ------------------------------------------------------------------ #


def list_alert_deliveries(
    ctx: OperationContext,
    request: ListAlertDeliveriesRequest,
) -> PagedResult[AlertDeliverySummary]:
    """List delivery attempts for an alert."""
    timer = start_timer()

    try:
        repo = _alert_repo(ctx)
        rows, total = repo.list_deliveries(
            alert_id=request.alert_id,
            channel_id=request.channel_id,
            status=request.status,
            limit=request.limit,
            offset=request.offset,
        )

        summaries = [_row_to_delivery_summary(r) for r in rows]
        return PagedResult.from_items(
            summaries,
            total=total,
            limit=request.limit,
            offset=request.offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return PagedResult(
            success=False,
            error=_err("INTERNAL", f"Failed to list alert deliveries: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _row_to_channel_summary(row: Any) -> AlertChannelSummary:

    if isinstance(row, dict):
        d = row
    elif hasattr(row, "keys"):
        d = dict(row)
    else:
        # Assume tuple in column order
        d = {
            "id": row[0],
            "name": row[1],
            "channel_type": row[2],
            "min_severity": row[4],
            "enabled": row[6],
            "consecutive_failures": row[10],
            "created_at": row[12],
        }

    return AlertChannelSummary(
        id=d.get("id", ""),
        name=d.get("name", ""),
        channel_type=d.get("channel_type", ""),
        min_severity=d.get("min_severity", "ERROR"),
        enabled=bool(d.get("enabled", 1)),
        consecutive_failures=d.get("consecutive_failures", 0),
        created_at=d.get("created_at"),
    )


def _row_to_channel_detail(row: Any) -> AlertChannelDetail:
    import json

    if isinstance(row, dict):
        d = row
    elif hasattr(row, "keys"):
        d = dict(row)
    else:
        d = {
            "id": row[0],
            "name": row[1],
            "channel_type": row[2],
            "config_json": row[3],
            "min_severity": row[4],
            "domains": row[5],
            "enabled": row[6],
            "throttle_minutes": row[7],
            "last_success_at": row[8],
            "last_failure_at": row[9],
            "consecutive_failures": row[10],
            "created_at": row[11],
            "updated_at": row[12],
        }

    config = d.get("config_json", {})
    if isinstance(config, str):
        config = json.loads(config)

    domains = d.get("domains")
    if isinstance(domains, str):
        domains = json.loads(domains)

    return AlertChannelDetail(
        id=d.get("id", ""),
        name=d.get("name", ""),
        channel_type=d.get("channel_type", ""),
        config=config,
        min_severity=d.get("min_severity", "ERROR"),
        domains=domains,
        enabled=bool(d.get("enabled", 1)),
        throttle_minutes=d.get("throttle_minutes", 5),
        last_success_at=d.get("last_success_at"),
        last_failure_at=d.get("last_failure_at"),
        consecutive_failures=d.get("consecutive_failures", 0),
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
    )


def _row_to_alert_summary(row: Any) -> AlertSummary:
    if isinstance(row, dict):
        d = row
    elif hasattr(row, "keys"):
        d = dict(row)
    else:
        d = {
            "id": row[0],
            "severity": row[1],
            "title": row[2],
            "message": row[3],
            "source": row[4],
            "domain": row[5],
            "created_at": row[10],
        }

    return AlertSummary(
        id=d.get("id", ""),
        severity=d.get("severity", ""),
        title=d.get("title", ""),
        message=d.get("message", ""),
        source=d.get("source", ""),
        domain=d.get("domain"),
        created_at=d.get("created_at"),
    )


def _row_to_delivery_summary(row: Any) -> AlertDeliverySummary:
    if isinstance(row, dict):
        d = row
    elif hasattr(row, "keys"):
        d = dict(row)
    else:
        d = {
            "id": row[0],
            "alert_id": row[1],
            "channel_id": row[2],
            "channel_name": row[3],
            "status": row[4],
            "attempted_at": row[5],
            "delivered_at": row[6],
            "error": row[8],
            "attempt": row[9],
        }

    return AlertDeliverySummary(
        id=d.get("id", ""),
        alert_id=d.get("alert_id", ""),
        channel_id=d.get("channel_id", ""),
        channel_name=d.get("channel_name", ""),
        status=d.get("status", ""),
        attempted_at=d.get("attempted_at"),
        delivered_at=d.get("delivered_at"),
        error=d.get("error"),
        attempt=d.get("attempt", 1),
    )


def _err(code: str, message: str):
    from spine.ops.result import OperationError
    return OperationError(code=code, message=message)
