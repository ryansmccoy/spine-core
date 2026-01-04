"""Dead Letter Queue API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from market_spine.execution.dlq import DLQManager
from market_spine.observability.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class DeadLetterResponse(BaseModel):
    """Dead letter entry response."""

    id: str
    execution_id: str
    pipeline: str
    params: dict[str, Any]
    error: str
    retry_count: int
    max_retries: int
    created_at: str
    last_retry_at: str | None
    resolved_at: str | None
    resolved_by: str | None
    can_retry: bool


class RetryResponse(BaseModel):
    """Retry result response."""

    dlq_id: str
    new_execution_id: str


@router.get("", response_model=list[DeadLetterResponse])
async def list_dead_letters(
    include_resolved: bool = Query(False, description="Include resolved entries"),
    limit: int = Query(100, le=1000, description="Max results"),
):
    """List dead letter entries."""
    try:
        dlq = DLQManager()
        entries = dlq.list_dead_letters(include_resolved=include_resolved, limit=limit)

        return [
            DeadLetterResponse(
                id=e.id,
                execution_id=e.execution_id,
                pipeline=e.pipeline,
                params=e.params,
                error=e.error,
                retry_count=e.retry_count,
                max_retries=e.max_retries,
                created_at=e.created_at.isoformat(),
                last_retry_at=e.last_retry_at.isoformat() if e.last_retry_at else None,
                resolved_at=e.resolved_at.isoformat() if e.resolved_at else None,
                resolved_by=e.resolved_by,
                can_retry=dlq.can_retry(e.id),
            )
            for e in entries
        ]
    except Exception as e:
        logger.error("list_dead_letters_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dlq_id}", response_model=DeadLetterResponse)
async def get_dead_letter(dlq_id: str):
    """Get dead letter entry by ID."""
    dlq = DLQManager()
    entry = dlq.get_dead_letter(dlq_id)

    if entry is None:
        raise HTTPException(status_code=404, detail="Dead letter not found")

    return DeadLetterResponse(
        id=entry.id,
        execution_id=entry.execution_id,
        pipeline=entry.pipeline,
        params=entry.params,
        error=entry.error,
        retry_count=entry.retry_count,
        max_retries=entry.max_retries,
        created_at=entry.created_at.isoformat(),
        last_retry_at=entry.last_retry_at.isoformat() if entry.last_retry_at else None,
        resolved_at=entry.resolved_at.isoformat() if entry.resolved_at else None,
        resolved_by=entry.resolved_by,
        can_retry=dlq.can_retry(entry.id),
    )


@router.post("/{dlq_id}/retry", response_model=RetryResponse)
async def retry_dead_letter(dlq_id: str):
    """
    Retry a dead letter entry.

    This creates a NEW execution with the same pipeline and parameters.
    The retry is submitted asynchronously via Celery.
    """
    from market_spine.celery_app import retry_dead_letter_task

    dlq = DLQManager()

    # Check if entry exists and can be retried
    entry = dlq.get_dead_letter(dlq_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Dead letter not found")

    if not dlq.can_retry(dlq_id):
        raise HTTPException(
            status_code=400,
            detail="Cannot retry: max retries exceeded or already resolved",
        )

    try:
        # Submit retry task
        result = retry_dead_letter_task.apply_async(args=[dlq_id])

        # Wait briefly for result (or return immediately)
        try:
            task_result = result.get(timeout=5)
            if "error" in task_result:
                raise HTTPException(status_code=400, detail=task_result["error"])
            return RetryResponse(
                dlq_id=dlq_id,
                new_execution_id=task_result["new_execution_id"],
            )
        except Exception:
            # Task is still running, return placeholder
            return RetryResponse(
                dlq_id=dlq_id,
                new_execution_id="pending",
            )

    except Exception as e:
        logger.error("retry_dead_letter_failed", dlq_id=dlq_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{dlq_id}/resolve", response_model=dict)
async def resolve_dead_letter(dlq_id: str, resolved_by: str = "manual"):
    """Manually resolve a dead letter without retrying."""
    dlq = DLQManager()

    entry = dlq.get_dead_letter(dlq_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Dead letter not found")

    if entry.resolved_at is not None:
        raise HTTPException(status_code=400, detail="Already resolved")

    dlq.resolve(dlq_id, resolved_by=resolved_by)

    return {"status": "resolved", "dlq_id": dlq_id, "resolved_by": resolved_by}
