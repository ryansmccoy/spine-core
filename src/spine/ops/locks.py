"""
Lock management operations.

Inspect and release concurrency locks.
Wraps :class:`~spine.execution.concurrency.ConcurrencyGuard`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from spine.core.logging import get_logger
from spine.core.repositories import LockRepository
from spine.ops.context import OperationContext
from spine.ops.requests import ListScheduleLocksRequest
from spine.ops.responses import ScheduleLockSummary
from spine.ops.result import OperationResult, PagedResult, start_timer

logger = get_logger(__name__)


def _lock_repo(ctx: OperationContext) -> LockRepository:
    return LockRepository(ctx.conn)


@dataclass(slots=True)
class LockSummary:
    """Active concurrency lock."""

    lock_key: str = ""
    owner: str = ""
    acquired_at: datetime | None = None
    expires_at: datetime | None = None


def list_locks(ctx: OperationContext) -> PagedResult[LockSummary]:
    """List all active concurrency locks."""
    timer = start_timer()

    try:
        repo = _lock_repo(ctx)
        rows = repo.list_locks()

        locks = [_row_to_lock(r) for r in rows]
        return PagedResult.from_items(
            locks, total=len(locks), elapsed_ms=timer.elapsed_ms
        )
    except Exception:
        # Table may not exist
        return PagedResult.from_items([], total=0, elapsed_ms=timer.elapsed_ms)


def release_lock(
    ctx: OperationContext,
    lock_key: str,
) -> OperationResult[None]:
    """Force-release a concurrency lock."""
    timer = start_timer()

    if not lock_key:
        return OperationResult.fail(
            "VALIDATION_FAILED", "lock_key is required", elapsed_ms=timer.elapsed_ms
        )

    if ctx.dry_run:
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)

    try:
        repo = _lock_repo(ctx)
        repo.release_lock(lock_key)
        ctx.conn.commit()
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL", f"Failed to release lock: {exc}", elapsed_ms=timer.elapsed_ms
        )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _row_to_lock(row: Any) -> LockSummary:
    if isinstance(row, dict):
        return LockSummary(
            lock_key=row.get("lock_key", ""),
            owner=row.get("owner", ""),
            acquired_at=row.get("acquired_at"),
            expires_at=row.get("expires_at"),
        )
    if hasattr(row, "keys"):
        d = dict(row)
        return LockSummary(
            lock_key=d.get("lock_key", ""),
            owner=d.get("owner", ""),
            acquired_at=d.get("acquired_at"),
            expires_at=d.get("expires_at"),
        )
    return LockSummary(lock_key=str(row[0]) if row else "")


# ------------------------------------------------------------------ #
# Schedule Locks (wires core_schedule_locks)
# ------------------------------------------------------------------ #


def list_schedule_locks(
    ctx: OperationContext,
    request: ListScheduleLocksRequest | None = None,
) -> PagedResult[ScheduleLockSummary]:
    """List active schedule locks.

    Schedule locks prevent multiple scheduler instances from triggering
    the same schedule simultaneously in distributed deployments.
    """

    timer = start_timer()
    limit = request.limit if request else 50
    offset = request.offset if request else 0

    try:
        repo = _lock_repo(ctx)
        rows, total = repo.list_schedule_locks()

        locks = [_row_to_schedule_lock(r) for r in rows]
        return PagedResult.from_items(
            locks,
            total=total,
            limit=limit,
            offset=offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception:
        # Table may not exist
        return PagedResult.from_items([], total=0, elapsed_ms=timer.elapsed_ms)


def release_schedule_lock(
    ctx: OperationContext,
    schedule_id: str,
) -> OperationResult[None]:
    """Force-release a schedule lock.

    Use with caution — releasing an active lock may allow duplicate
    schedule executions.
    """
    timer = start_timer()

    if not schedule_id:
        return OperationResult.fail(
            "VALIDATION_FAILED", "schedule_id is required", elapsed_ms=timer.elapsed_ms
        )

    if ctx.dry_run:
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)

    try:
        repo = _lock_repo(ctx)
        repo.release_schedule_lock(schedule_id)
        ctx.conn.commit()
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL", f"Failed to release schedule lock: {exc}", elapsed_ms=timer.elapsed_ms
        )


def _row_to_schedule_lock(row: Any) -> ScheduleLockSummary:
    if isinstance(row, dict):
        return ScheduleLockSummary(
            schedule_id=row.get("schedule_id", ""),
            locked_by=row.get("locked_by", ""),
            locked_at=row.get("locked_at"),
            expires_at=row.get("expires_at"),
        )
    if hasattr(row, "keys"):
        d = dict(row)
        return ScheduleLockSummary(
            schedule_id=d.get("schedule_id", ""),
            locked_by=d.get("locked_by", ""),
            locked_at=d.get("locked_at"),
            expires_at=d.get("expires_at"),
        )
    return ScheduleLockSummary(
        schedule_id=str(row[0]) if row else "",
        locked_by=str(row[1]) if len(row) > 1 else "",
        locked_at=row[2] if len(row) > 2 else None,
        expires_at=row[3] if len(row) > 3 else None,
    )
