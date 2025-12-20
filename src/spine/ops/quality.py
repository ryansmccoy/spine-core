"""
Quality result operations.

Read-only access to quality check results written by workflow runs.
Wraps :mod:`spine.core.quality`.

The ``core_quality`` table stores individual check results (one row per check).
This module aggregates them into per-domain summaries for the API:
``workflow`` = domain, ``checks_passed`` / ``checks_failed`` = counts,
``score`` = passed / total, ``run_at`` = latest ``created_at``.
"""

from __future__ import annotations

from typing import Any

from spine.core.logging import get_logger

from spine.core.repositories import QualityRepository
from spine.ops.context import OperationContext
from spine.ops.requests import ListQualityResultsRequest
from spine.ops.responses import QualityResultSummary
from spine.ops.result import PagedResult, start_timer

logger = get_logger(__name__)


def _quality_repo(ctx: OperationContext) -> QualityRepository:
    return QualityRepository(ctx.conn)

# ------------------------------------------------------------------ #
# The actual table is ``core_quality`` (created by spine.core.schema).
# Each row is a single quality-check result with columns:
#   domain, partition_key, check_name, category, status, message,
#   actual_value, expected_value, details_json, execution_id,
#   batch_id, created_at
#
# The API returns *aggregated* summaries grouped by domain.
# ------------------------------------------------------------------ #

_COUNT_SQL = """
    SELECT COUNT(DISTINCT domain) FROM core_quality WHERE {where}
"""

_SUMMARY_SQL = """
    SELECT
        domain AS workflow,
        SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) AS checks_passed,
        SUM(CASE WHEN status != 'PASS' THEN 1 ELSE 0 END) AS checks_failed,
        ROUND(
            CAST(SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) AS REAL)
            / MAX(COUNT(*), 1),
            4
        ) AS score,
        MAX(created_at) AS run_at
    FROM core_quality
    WHERE {where}
    GROUP BY domain
    ORDER BY run_at DESC
    LIMIT ? OFFSET ?
"""


def list_quality_results(
    ctx: OperationContext,
    request: ListQualityResultsRequest,
) -> PagedResult[QualityResultSummary]:
    """List quality-check results aggregated by domain."""
    timer = start_timer()

    try:
        repo = _quality_repo(ctx)
        rows, total = repo.aggregate_by_workflow(
            workflow=request.workflow,
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
            error=_err("INTERNAL", f"Failed to list quality results: {exc}"),
            elapsed_ms=timer.elapsed_ms,
        )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _row_to_summary(row: Any) -> QualityResultSummary:
    if isinstance(row, dict):
        return QualityResultSummary(
            workflow=row.get("workflow", ""),
            checks_passed=row.get("checks_passed", 0),
            checks_failed=row.get("checks_failed", 0),
            score=row.get("score", 0.0),
            run_at=row.get("run_at"),
        )
    if hasattr(row, "keys"):
        d = dict(row)
        return QualityResultSummary(
            workflow=d.get("workflow", ""),
            checks_passed=d.get("checks_passed", 0),
            checks_failed=d.get("checks_failed", 0),
            score=d.get("score", 0.0),
            run_at=d.get("run_at"),
        )
    return QualityResultSummary()


def _err(code: str, message: str):
    from spine.ops.result import OperationError
    return OperationError(code=code, message=message)
