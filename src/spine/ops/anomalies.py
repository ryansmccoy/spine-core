"""
Anomaly operations.

Read-only access to detected anomalies.  Wraps :mod:`spine.core.anomalies`.
"""

from __future__ import annotations

from typing import Any

from spine.core.logging import get_logger
from spine.core.repositories import AnomalyRepository
from spine.ops.context import OperationContext
from spine.ops.requests import ListAnomaliesRequest
from spine.ops.responses import AnomalySummary
from spine.ops.result import PagedResult, start_timer

logger = get_logger(__name__)


def _anomaly_repo(ctx: OperationContext) -> AnomalyRepository:
    return AnomalyRepository(ctx.conn)


def list_anomalies(
    ctx: OperationContext,
    request: ListAnomaliesRequest,
) -> PagedResult[AnomalySummary]:
    """List detected anomalies with optional filtering."""
    timer = start_timer()

    try:
        repo = _anomaly_repo(ctx)
        rows, total = repo.list_anomalies(
            workflow=request.workflow,
            severity=request.severity,
            since=request.since.isoformat() if request.since else None,
            limit=request.limit,
            offset=request.offset,
        )

        summaries = [_row_to_summary(r) for r in rows]
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
            error=_err("INTERNAL", f"Failed to list anomalies: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _row_to_summary(row: Any) -> AnomalySummary:
    if isinstance(row, dict):
        return AnomalySummary(
            id=row.get("id", ""),
            workflow=row.get("workflow", ""),
            metric=row.get("metric", ""),
            severity=row.get("severity", ""),
            value=row.get("value", 0.0),
            threshold=row.get("threshold", 0.0),
            detected_at=row.get("detected_at"),
        )
    if hasattr(row, "keys"):
        d = dict(row)
        return AnomalySummary(
            id=d.get("id", ""),
            workflow=d.get("workflow", ""),
            metric=d.get("metric", ""),
            severity=d.get("severity", ""),
            value=d.get("value", 0.0),
            threshold=d.get("threshold", 0.0),
            detected_at=d.get("detected_at"),
        )
    return AnomalySummary()


def _err(code: str, message: str):
    from spine.ops.result import OperationError
    return OperationError(code=code, message=message)
