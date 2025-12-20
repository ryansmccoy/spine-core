"""
Workflow data operations.

CRUD for manifest entries, rejects, and work items.
Wires ``core_manifest``, ``core_rejects``, and ``core_work_items`` tables
to the API/CLI.

These tables track workflow execution artifacts:

- **Manifest**: Stage completion status per domain/partition
- **Rejects**: Bad records that failed validation
- **Work items**: Scheduled/queued work for workflow execution
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from spine.core.logging import get_logger

from spine.core.repositories import ManifestRepository, RejectRepository, WorkItemRepository
from spine.ops.context import OperationContext
from spine.ops.requests import (
    ClaimWorkItemRequest,
    ListManifestEntriesRequest,
    ListRejectsRequest,
    ListWorkItemsRequest,
)
from spine.ops.responses import (
    ManifestEntrySummary,
    RejectSummary,
    WorkItemSummary,
)
from spine.ops.result import OperationResult, PagedResult, start_timer

logger = get_logger(__name__)


def _manifest_repo(ctx: OperationContext) -> ManifestRepository:
    return ManifestRepository(ctx.conn)


def _reject_repo(ctx: OperationContext) -> RejectRepository:
    return RejectRepository(ctx.conn)


def _work_item_repo(ctx: OperationContext) -> WorkItemRepository:
    return WorkItemRepository(ctx.conn)


# ------------------------------------------------------------------ #
# Manifest (wires core_manifest)
# ------------------------------------------------------------------ #


def list_manifest_entries(
    ctx: OperationContext,
    request: ListManifestEntriesRequest | None = None,
) -> PagedResult[ManifestEntrySummary]:
    """List manifest entries (workflow stage completion status).

    The manifest tracks which stages have completed for each
    domain/partition combination, enabling resume-from-last-good-state
    and auditing.
    """
    timer = start_timer()
    limit = request.limit if request else 100
    offset = request.offset if request else 0

    try:
        since_str = None
        if request and request.since:
            since_str = request.since.isoformat() if isinstance(request.since, datetime) else request.since

        repo = _manifest_repo(ctx)
        rows, total = repo.list_entries(
            domain=request.domain if request else None,
            partition_key=request.partition_key if request else None,
            stage=request.stage if request else None,
            since=since_str,
            limit=limit,
            offset=offset,
        )

        summaries = [
            ManifestEntrySummary(
                domain=r.get("domain", ""),
                partition_key=r.get("partition_key", ""),
                stage=r.get("stage", ""),
                stage_rank=r.get("stage_rank"),
                row_count=r.get("row_count"),
                execution_id=r.get("execution_id"),
                batch_id=r.get("batch_id"),
                updated_at=r.get("updated_at"),
            )
            for r in rows
        ]

        return PagedResult.from_items(
            summaries,
            total=total,
            limit=limit,
            offset=offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception:
        # Table may not exist
        return PagedResult.from_items([], total=0, elapsed_ms=timer.elapsed_ms)


def get_manifest_entry(
    ctx: OperationContext,
    domain: str,
    partition_key: str,
    stage: str,
) -> OperationResult[ManifestEntrySummary]:
    """Get a single manifest entry."""
    timer = start_timer()

    if not domain or not partition_key or not stage:
        return OperationResult.fail(
            "VALIDATION_FAILED",
            "domain, partition_key, and stage are required",
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        repo = _manifest_repo(ctx)
        row = repo.get_entry(domain, partition_key, stage)

        if not row:
            return OperationResult.fail(
                "NOT_FOUND",
                f"Manifest entry not found: {domain}/{partition_key}/{stage}",
                elapsed_ms=timer.elapsed_ms,
            )

        summary = ManifestEntrySummary(
            domain=row.get("domain", ""),
            partition_key=row.get("partition_key", ""),
            stage=row.get("stage", ""),
            stage_rank=row.get("stage_rank"),
            row_count=row.get("row_count"),
            execution_id=row.get("execution_id"),
            batch_id=row.get("batch_id"),
            updated_at=row.get("updated_at"),
        )
        return OperationResult.ok(summary, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to get manifest entry: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Rejects (wires core_rejects)
# ------------------------------------------------------------------ #


def list_rejects(
    ctx: OperationContext,
    request: ListRejectsRequest | None = None,
) -> PagedResult[RejectSummary]:
    """List rejected records from workflow processing.

    Rejects are records that failed validation during ingestion
    or transformation. Useful for debugging data quality issues.
    """
    timer = start_timer()
    limit = request.limit if request else 100
    offset = request.offset if request else 0

    try:
        since_str = None
        if request and request.since:
            since_str = request.since.isoformat() if isinstance(request.since, datetime) else request.since

        repo = _reject_repo(ctx)
        rows, total = repo.list_rejects(
            domain=request.domain if request else None,
            partition_key=request.partition_key if request else None,
            stage=request.stage if request else None,
            reason_code=request.reason_code if request else None,
            execution_id=request.execution_id if request else None,
            since=since_str,
            limit=limit,
            offset=offset,
        )

        summaries = [
            RejectSummary(
                domain=r.get("domain", ""),
                partition_key=r.get("partition_key", ""),
                stage=r.get("stage", ""),
                reason_code=r.get("reason_code", ""),
                reason_detail=r.get("reason_detail"),
                record_key=r.get("record_key"),
                source_locator=r.get("source_locator"),
                line_number=r.get("line_number"),
                execution_id=r.get("execution_id", ""),
                created_at=r.get("created_at"),
            )
            for r in rows
        ]

        return PagedResult.from_items(
            summaries,
            total=total,
            limit=limit,
            offset=offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception:
        # Table may not exist
        return PagedResult.from_items([], total=0, elapsed_ms=timer.elapsed_ms)


def count_rejects_by_reason(
    ctx: OperationContext,
    domain: str | None = None,
    partition_key: str | None = None,
) -> OperationResult[list[dict[str, Any]]]:
    """Count rejects grouped by reason code.

    Useful for reject analysis dashboards.
    """
    timer = start_timer()

    try:
        repo = _reject_repo(ctx)
        rows = repo.count_by_reason(
            domain=domain,
            partition_key=partition_key,
        )

        counts = [
            {"reason_code": r.get("reason_code", ""), "count": r.get("cnt", 0)}
            for r in rows
        ]
        return OperationResult.ok(counts, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to count rejects: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Work Items (wires core_work_items)
# ------------------------------------------------------------------ #


def list_work_items(
    ctx: OperationContext,
    request: ListWorkItemsRequest | None = None,
) -> PagedResult[WorkItemSummary]:
    """List work items (scheduled workflow work).

    Work items represent pending or in-progress workflow executions.
    Used for job queue management and work distribution.
    """
    timer = start_timer()
    limit = request.limit if request else 100
    offset = request.offset if request else 0

    try:
        repo = _work_item_repo(ctx)
        rows, total = repo.list_items(
            domain=request.domain if request else None,
            workflow=request.workflow if request else None,
            state=request.state if request else None,
            limit=limit,
            offset=offset,
        )

        summaries = [
            WorkItemSummary(
                id=r.get("id", 0),
                domain=r.get("domain", ""),
                workflow=r.get("workflow", ""),
                partition_key=r.get("partition_key", ""),
                state=r.get("state", "PENDING"),
                priority=r.get("priority", 100),
                desired_at=r.get("desired_at"),
                attempt_count=r.get("attempt_count", 0),
                max_attempts=r.get("max_attempts", 3),
                last_error=r.get("last_error"),
                locked_by=r.get("locked_by"),
                created_at=r.get("created_at"),
                updated_at=r.get("updated_at"),
            )
            for r in rows
        ]

        return PagedResult.from_items(
            summaries,
            total=total,
            limit=limit,
            offset=offset,
            elapsed_ms=timer.elapsed_ms,
        )
    except Exception:
        # Table may not exist
        return PagedResult.from_items([], total=0, elapsed_ms=timer.elapsed_ms)


def claim_work_item(
    ctx: OperationContext,
    request: ClaimWorkItemRequest,
) -> OperationResult[WorkItemSummary]:
    """Claim a work item for processing.

    Atomically marks a PENDING work item as RUNNING and assigns
    it to the given worker_id.
    """
    timer = start_timer()

    if not request.item_id or not request.worker_id:
        return OperationResult.fail(
            "VALIDATION_FAILED",
            "item_id and worker_id are required",
            elapsed_ms=timer.elapsed_ms,
        )

    if ctx.dry_run:
        return OperationResult.ok(
            WorkItemSummary(id=request.item_id, state="RUNNING", locked_by=request.worker_id),
            elapsed_ms=timer.elapsed_ms,
        )

    try:
        now = datetime.utcnow().isoformat()

        repo = _work_item_repo(ctx)
        row = repo.claim(request.item_id, request.worker_id, now)
        ctx.conn.commit()

        if not row:
            return OperationResult.fail(
                "NOT_FOUND",
                f"Work item {request.item_id} not found",
                elapsed_ms=timer.elapsed_ms,
            )

        state = row.get("state", "")
        if state != "RUNNING":
            return OperationResult.fail(
                "CONFLICT",
                f"Work item {request.item_id} is not PENDING (state={state})",
                elapsed_ms=timer.elapsed_ms,
            )

        summary = WorkItemSummary(
            id=row.get("id", 0),
            domain=row.get("domain", ""),
            workflow=row.get("workflow", ""),
            partition_key=row.get("partition_key", ""),
            state=row.get("state", "RUNNING"),
            priority=row.get("priority", 100),
            desired_at=row.get("desired_at"),
            attempt_count=row.get("attempt_count", 0),
            max_attempts=row.get("max_attempts", 3),
            last_error=row.get("last_error"),
            locked_by=row.get("locked_by"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
        return OperationResult.ok(summary, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL",
            f"Failed to claim work item: {exc}",
            elapsed_ms=timer.elapsed_ms,
        )


def complete_work_item(
    ctx: OperationContext,
    item_id: int,
    execution_id: str | None = None,
) -> OperationResult[None]:
    """Mark a work item as completed."""
    timer = start_timer()

    if not item_id:
        return OperationResult.fail(
            "VALIDATION_FAILED", "item_id is required", elapsed_ms=timer.elapsed_ms
        )

    if ctx.dry_run:
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)

    try:
        now = datetime.utcnow().isoformat()
        repo = _work_item_repo(ctx)
        repo.complete(item_id, now, execution_id=execution_id)
        ctx.conn.commit()
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL", f"Failed to complete work item: {exc}", elapsed_ms=timer.elapsed_ms
        )


def fail_work_item(
    ctx: OperationContext,
    item_id: int,
    error: str,
) -> OperationResult[None]:
    """Mark a work item as failed.

    If max_attempts not reached, state becomes RETRY_WAIT for
    exponential backoff retry.
    """
    timer = start_timer()

    if not item_id:
        return OperationResult.fail(
            "VALIDATION_FAILED", "item_id is required", elapsed_ms=timer.elapsed_ms
        )

    if ctx.dry_run:
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)

    try:
        now = datetime.utcnow().isoformat()

        # Check current attempt count vs max
        repo = _work_item_repo(ctx)
        row = repo.get_by_id(item_id)
        if not row:
            return OperationResult.fail(
                "NOT_FOUND", f"Work item {item_id} not found", elapsed_ms=timer.elapsed_ms
            )

        attempt_count = row.get("attempt_count", 0)
        max_attempts = row.get("max_attempts", 3)

        if attempt_count >= max_attempts:
            new_state = "FAILED"
        else:
            new_state = "RETRY_WAIT"

        repo.fail(item_id, error, now, new_state=new_state)
        ctx.conn.commit()
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL", f"Failed to fail work item: {exc}", elapsed_ms=timer.elapsed_ms
        )


def cancel_work_item(
    ctx: OperationContext,
    item_id: int,
) -> OperationResult[None]:
    """Cancel a work item (mark as CANCELLED)."""
    timer = start_timer()

    if not item_id:
        return OperationResult.fail(
            "VALIDATION_FAILED", "item_id is required", elapsed_ms=timer.elapsed_ms
        )

    if ctx.dry_run:
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)

    try:
        now = datetime.utcnow().isoformat()
        repo = _work_item_repo(ctx)
        repo.cancel(item_id, now)
        ctx.conn.commit()
        return OperationResult.ok(None, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL", f"Failed to cancel work item: {exc}", elapsed_ms=timer.elapsed_ms
        )


def retry_failed_work_items(
    ctx: OperationContext,
    domain: str | None = None,
) -> OperationResult[int]:
    """Reset FAILED work items to PENDING for retry.

    Returns the count of items reset.
    """
    timer = start_timer()

    if ctx.dry_run:
        try:
            repo = _work_item_repo(ctx)
            # Count failed items that would be retried
            _, count = repo.list_items(domain=domain, state="FAILED", limit=0)
            return OperationResult.ok(count, elapsed_ms=timer.elapsed_ms)
        except Exception:
            logger.exception("op_failed")
            return OperationResult.ok(0, elapsed_ms=timer.elapsed_ms)

    try:
        now = datetime.utcnow().isoformat()
        repo = _work_item_repo(ctx)
        count = repo.retry_failed(domain=domain, now=now)
        ctx.conn.commit()
        return OperationResult.ok(count, elapsed_ms=timer.elapsed_ms)
    except Exception as exc:
        logger.exception("op_failed", error=str(exc))
        return OperationResult.fail(
            "INTERNAL", f"Failed to retry work items: {exc}", elapsed_ms=timer.elapsed_ms
        )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _col(row: Any, idx: int, name: str, default: Any = "") -> Any:
    """Extract a column from a row that may be a dict, Row, or tuple."""
    if isinstance(row, dict):
        return row.get(name, default)
    if hasattr(row, "keys"):
        return dict(row).get(name, default)
    try:
        return row[idx]
    except (IndexError, TypeError):
        return default
