"""
Dead letter queue operations.

Wraps :class:`~spine.execution.dlq.DLQManager` with typed contracts.
"""

from __future__ import annotations

from typing import Any

from spine.core.logging import get_logger

from spine.core.repositories import DeadLetterRepository
from spine.ops.context import OperationContext
from spine.ops.requests import ListDeadLettersRequest, ReplayDeadLetterRequest
from spine.ops.responses import DeadLetterSummary
from spine.ops.result import OperationResult, PagedResult, start_timer

logger = get_logger(__name__)


def _dlq_repo(ctx: OperationContext) -> DeadLetterRepository:
    return DeadLetterRepository(ctx.conn)


def list_dead_letters(
    ctx: OperationContext,
    request: ListDeadLettersRequest,
) -> PagedResult[DeadLetterSummary]:
    """List dead-lettered executions."""
    timer = start_timer()

    try:
        repo = _dlq_repo(ctx)
        rows, total = repo.list_dead_letters(
            workflow=request.workflow,
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
            error=_err("INTERNAL", f"Failed to list dead letters: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


def replay_dead_letter(
    ctx: OperationContext,
    request: ReplayDeadLetterRequest,
) -> OperationResult[None]:
    """Re-queue a dead-lettered execution for replay.

    Increments the replay_count and resets the item for reprocessing.
    """
    timer = start_timer()

    if not request.dead_letter_id:
        return OperationResult.fail(
            "VALIDATION_FAILED", "dead_letter_id is required", elapsed_ms=timer.elapsed_ms
        )

    if ctx.dry_run:
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)

    try:
        repo = _dlq_repo(ctx)
        if not repo.exists(request.dead_letter_id):
            return OperationResult.fail(
                "NOT_FOUND",
                f"Dead letter '{request.dead_letter_id}' not found",
                elapsed_ms=timer.elapsed_ms,
            )

        repo.increment_replay(request.dead_letter_id)
        ctx.conn.commit()
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL", f"Failed to replay dead letter: {exc}", elapsed_ms=timer.elapsed_ms
        )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _row_to_summary(row: Any) -> DeadLetterSummary:
    if isinstance(row, dict):
        return DeadLetterSummary(
            id=row.get("id", ""),
            workflow=row.get("workflow", ""),
            error=row.get("error", ""),
            created_at=row.get("created_at"),
            replay_count=row.get("replay_count", 0),
        )
    if hasattr(row, "keys"):
        d = dict(row)
        return DeadLetterSummary(
            id=d.get("id", ""),
            workflow=d.get("workflow", ""),
            error=d.get("error", ""),
            created_at=d.get("created_at"),
            replay_count=d.get("replay_count", 0),
        )
    return DeadLetterSummary(id=str(row[0]) if row else "")


def _err(code: str, message: str):
    from spine.ops.result import OperationError
    return OperationError(code=code, message=message)
