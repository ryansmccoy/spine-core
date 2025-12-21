"""
Anomaly router — view detected metric anomalies.

Provides read access to anomaly detection results for workflow metrics.
Anomalies represent values that breach expected thresholds.

Endpoints:
    GET /anomalies    List detected anomalies with filtering

Manifesto:
    Surfacing data anomalies through the API gives dashboards
    real-time visibility into quality issues without polling the DB.

Tags:
    spine-core, api, anomalies, data-quality, detection

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from spine.api.deps import OpContext
from spine.api.schemas.common import PagedResponse, PageMeta
from spine.api.schemas.domains import AnomalySchema
from spine.api.utils import _dc, _handle_error

router = APIRouter(prefix="/anomalies")


@router.get("", response_model=PagedResponse[AnomalySchema])
def list_anomalies(
    ctx: OpContext,
    workflow: str | None = Query(None, description="Filter by workflow name"),
    severity: str | None = Query(None, description="Filter by severity: 'info' | 'warning' | 'critical'"),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return (1-500)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List detected anomalies with optional filtering.

    Returns metric anomalies that have breached defined thresholds.
    Severity levels indicate required action urgency.

    Args:
        ctx: Operation context with database connection.
        workflow: Optional filter by workflow name.
        severity: Optional filter by severity level.
        limit: Maximum items per page (default 50, max 500).
        offset: Pagination offset (default 0).

    Returns:
        PagedResponse containing list of AnomalySchema items.

    Example:
        GET /api/v1/anomalies?severity=critical

        Response:
        {
            "data": [
                {
                    "id": "anom-123",
                    "workflow": "daily_etl",
                    "metric": "row_count",
                    "severity": "critical",
                    "value": 0,
                    "threshold": 1000,
                    "detected_at": "2026-02-13T10:30:00Z"
                }
            ],
            "page": {"total": 1, "limit": 50, "offset": 0, "has_more": false}
        }
    """
    from spine.ops.anomalies import list_anomalies as _list
    from spine.ops.requests import ListAnomaliesRequest

    request = ListAnomaliesRequest(workflow=workflow, severity=severity, limit=limit, offset=offset)
    result = _list(ctx, request)
    if not result.success:
        return _handle_error(result)
    items = [AnomalySchema(**_dc(a)) for a in (result.data or [])]
    return PagedResponse(
        data=items,
        page=PageMeta(
            total=result.total or len(items),
            limit=result.limit or limit,
            offset=result.offset or offset,
            has_more=result.has_more or False,
        ),
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )
