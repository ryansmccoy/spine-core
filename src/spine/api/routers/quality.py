"""
Quality router — view workflow quality check results.

Provides read access to quality check results for data workflows.
Quality checks validate data completeness, freshness, and correctness.

Endpoints:
    GET /quality    List quality check results with filtering

Manifesto:
    Data quality metrics should be accessible via API so dashboards
    can display freshness, completeness, and accuracy scores.

Tags:
    spine-core, api, quality, metrics, data-freshness

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from spine.api.deps import OpContext
from spine.api.schemas.common import PagedResponse, PageMeta
from spine.api.schemas.domains import QualityResultSchema
from spine.api.utils import _dc, _handle_error

router = APIRouter(prefix="/quality")


@router.get("", response_model=PagedResponse[QualityResultSchema])
def list_quality_results(
    ctx: OpContext,
    workflow: str | None = Query(None, description="Filter by workflow name"),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return (1-500)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List quality check results with optional filtering.

    Returns quality scores and check pass/fail counts for workflows.
    Use for quality dashboards and monitoring views.

    Args:
        ctx: Operation context with database connection.
        workflow: Optional filter by workflow name.
        limit: Maximum items per page (default 50, max 500).
        offset: Pagination offset (default 0).

    Returns:
        PagedResponse containing list of QualityResultSchema items.

    Example:
        GET /api/v1/quality?workflow=daily_etl

        Response:
        {
            "data": [
                {
                    "workflow": "daily_etl",
                    "checks_passed": 8,
                    "checks_failed": 1,
                    "score": 88.9,
                    "run_at": "2026-02-13T10:00:00Z"
                }
            ],
            "page": {"total": 1, "limit": 50, "offset": 0, "has_more": false}
        }
    """
    from spine.ops.quality import list_quality_results as _list
    from spine.ops.requests import ListQualityResultsRequest

    request = ListQualityResultsRequest(workflow=workflow, limit=limit, offset=offset)
    result = _list(ctx, request)
    if not result.success:
        return _handle_error(result)
    items = [QualityResultSchema(**_dc(q)) for q in (result.data or [])]
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
