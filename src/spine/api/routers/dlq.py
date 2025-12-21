"""
Dead-letter queue router — manage failed items after retry exhaustion.

Provides operations to view and replay items that have failed permanently
after exhausting all retry attempts.

Endpoints:
    GET  /dlq              List dead-letter entries with filtering
    POST /dlq/{id}/replay  Replay a dead-letter item (re-queue for execution)

Manifesto:
    Failed executions must be inspectable and retryable through
    the API so operators don't need direct database access.

Tags:
    spine-core, api, dead-letter-queue, retry, failure-management

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from fastapi import APIRouter, Path, Query

from spine.api.deps import OpContext
from spine.api.schemas.common import PagedResponse, PageMeta, SuccessResponse
from spine.api.schemas.domains import DeadLetterSchema
from spine.api.utils import _dc, _handle_error

router = APIRouter(prefix="/dlq")


@router.get("", response_model=PagedResponse[DeadLetterSchema])
def list_dead_letters(
    ctx: OpContext,
    workflow: str | None = Query(None, description="Filter by source workflow name"),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return (1-500)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List dead-letter entries with optional filtering.

    Returns items that have failed permanently after exhausting retry attempts.
    Use this for the DLQ management view in the orchestration console.

    Args:
        ctx: Operation context with database connection.
        workflow: Optional filter by source workflow name.
        limit: Maximum items per page (default 50, max 500).
        offset: Pagination offset (default 0).

    Returns:
        PagedResponse containing list of DeadLetterSchema items.

    Example:
        GET /api/v1/dlq?workflow=daily_etl&limit=10

        Response:
        {
            "data": [
                {
                    "id": "dlq-123",
                    "workflow": "daily_etl",
                    "error": "Connection timeout to warehouse",
                    "created_at": "2026-02-13T10:30:00Z",
                    "replay_count": 0
                }
            ],
            "page": {"total": 5, "limit": 10, "offset": 0, "has_more": false}
        }
    """
    from spine.ops.dlq import list_dead_letters as _list
    from spine.ops.requests import ListDeadLettersRequest

    request = ListDeadLettersRequest(workflow=workflow, limit=limit, offset=offset)
    result = _list(ctx, request)
    if not result.success:
        return _handle_error(result)
    items = [DeadLetterSchema(**_dc(d)) for d in (result.data or [])]
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


@router.post("/{item_id}/replay", response_model=SuccessResponse[dict])
def replay_dead_letter(ctx: OpContext, item_id: str = Path(..., description="Dead-letter entry ID")):
    """Replay a dead-letter entry.

    Re-queues the failed item for another execution attempt. The original
    parameters and context are preserved. Increments the replay_count.

    Args:
        ctx: Operation context with database connection.
        item_id: The dead-letter entry identifier.

    Returns:
        SuccessResponse with replay confirmation.

    Raises:
        404 NOT_FOUND: Dead-letter entry does not exist.

    Example:
        POST /api/v1/dlq/dlq-123/replay

        Response:
        {"data": {"replayed": true, "id": "dlq-123", "new_run_id": "run-456"}}
    """
    from spine.ops.dlq import replay_dead_letter as _replay
    from spine.ops.requests import ReplayDeadLetterRequest

    result = _replay(ctx, ReplayDeadLetterRequest(dead_letter_id=item_id))
    if not result.success:
        return _handle_error(result)
    data = _dc(result.data) if result.data else {"replayed": True, "id": item_id}
    return SuccessResponse(
        data=data,
        elapsed_ms=result.elapsed_ms,
        warnings=result.warnings,
    )
