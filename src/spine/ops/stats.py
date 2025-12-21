"""
Stats operations — query execution statistics and queue depths.

Extracted from ``api/routers/stats.py`` to enforce the
CLI/API → ops → db layering contract (SMELL-LAYER-0003).

Doc-Types: OPS_MODULE
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_run_stats(conn) -> dict[str, int]:
    """Return aggregate run counts grouped by status.

    Args:
        conn: Database connection (cursor-like) supporting
              ``.execute()`` and ``.fetchall()``.

    Returns:
        Dict mapping status names to counts, plus ``"total"`` key.
        Returns zeroed-out dict on query failure.
    """
    try:
        conn.execute(
            "SELECT status, COUNT(*) AS cnt "
            "FROM core_executions GROUP BY status"
        )
        rows = conn.fetchall()
    except Exception:
        logger.exception("Failed to fetch run stats from database")
        rows = []

    counts: dict[str, int] = {}
    total = 0
    for row in rows:
        if isinstance(row, dict):
            s, c = row.get("status", ""), row.get("cnt", 0)
        elif hasattr(row, "keys"):
            d = dict(row)
            s, c = d.get("status", ""), d.get("cnt", 0)
        else:
            s, c = (row[0] if row else ""), (row[1] if len(row) > 1 else 0)
        counts[s] = c
        total += c

    counts["total"] = total
    return counts


def get_queue_depths(conn) -> list[dict[str, Any]]:
    """Return pending/running counts per priority lane.

    Args:
        conn: Database connection (cursor-like) supporting
              ``.execute()`` and ``.fetchall()``.

    Returns:
        List of dicts ``{"lane": ..., "pending": ..., "running": ...}``.
        Returns empty list on query failure.
    """
    try:
        conn.execute(
            "SELECT lane, status, COUNT(*) AS cnt "
            "FROM core_executions "
            "WHERE status IN ('pending', 'running') "
            "GROUP BY lane, status"
        )
        rows = conn.fetchall()
    except Exception:
        logger.exception("Failed to fetch queue depths from database")
        rows = []

    lane_data: dict[str, dict[str, int]] = {}
    for row in rows:
        if isinstance(row, dict):
            lane, status, cnt = (
                row.get("lane", "default"),
                row.get("status", ""),
                row.get("cnt", 0),
            )
        elif hasattr(row, "keys"):
            d = dict(row)
            lane, status, cnt = (
                d.get("lane", "default"),
                d.get("status", ""),
                d.get("cnt", 0),
            )
        else:
            lane = row[0] if row else "default"
            status = row[1] if len(row) > 1 else ""
            cnt = row[2] if len(row) > 2 else 0

        lane = lane or "default"
        if lane not in lane_data:
            lane_data[lane] = {"pending": 0, "running": 0}
        if status in ("pending", "running"):
            lane_data[lane][status] = cnt

    return [
        {"lane": lane, "pending": d["pending"], "running": d["running"]}
        for lane, d in sorted(lane_data.items())
    ]


def get_run_history(conn, *, hours: int = 24, buckets: int = 24) -> list[dict[str, Any]]:
    """Return run counts bucketed into time intervals for the activity chart.

    Divides the last ``hours`` hours into ``buckets`` equal intervals and
    counts runs per status in each bucket.

    Args:
        conn: Database connection supporting ``.execute()`` / ``.fetchall()``.
        hours: Look-back window in hours (default 24).
        buckets: Number of time buckets to produce (default 24).

    Returns:
        List of dicts with keys ``bucket`` (ISO-8601 start of interval),
        ``completed``, ``failed``, ``running``, ``cancelled``.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    interval_secs = (hours * 3600) / max(buckets, 1)
    start = now - timedelta(hours=hours)

    # Build empty buckets
    bucket_starts: list[datetime] = []
    for i in range(buckets):
        bucket_starts.append(start + timedelta(seconds=i * interval_secs))

    result: list[dict[str, Any]] = [
        {
            "bucket": bs.isoformat(),
            "completed": 0,
            "failed": 0,
            "running": 0,
            "cancelled": 0,
        }
        for bs in bucket_starts
    ]

    try:
        conn.execute(
            "SELECT status, started_at FROM core_executions "
            "WHERE started_at IS NOT NULL AND started_at >= ?",
            (start.isoformat(),),
        )
        rows = conn.fetchall()
    except Exception:
        logger.exception("Failed to fetch run history")
        return result

    for row in rows:
        if isinstance(row, dict):
            status = row.get("status", "")
            ts_str = row.get("started_at", "")
        elif hasattr(row, "keys"):
            d = dict(row)
            status = d.get("status", "")
            ts_str = d.get("started_at", "")
        else:
            status = row[0] if row else ""
            ts_str = row[1] if len(row) > 1 else ""

        if not ts_str:
            continue

        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        # Find the bucket this run belongs to
        offset_secs = (ts - start).total_seconds()
        idx = int(offset_secs / interval_secs)
        if idx < 0:
            idx = 0
        elif idx >= buckets:
            idx = buckets - 1

        key = status if status in ("completed", "failed", "running", "cancelled") else None
        if key:
            result[idx][key] += 1

    return result


# ── Worker stats (delegated to execution layer) ────────────────────


def get_active_workers() -> list:
    """Get active workers via the execution layer.

    Returns:
        List of worker info objects from ``spine.execution.worker``.
        Returns empty list if execution module is unavailable.
    """
    try:
        from spine.execution.worker import get_active_workers as _get_active_workers

        return _get_active_workers()
    except ImportError:
        logger.debug("spine.execution.worker not available")
        return []
    except Exception:
        logger.exception("Failed to fetch active workers")
        return []


def get_worker_stats() -> list[dict[str, Any]]:
    """Get aggregate worker statistics via the execution layer.

    Returns:
        List of worker stat dicts from ``spine.execution.worker``.
        Returns empty list if execution module is unavailable.
    """
    try:
        from spine.execution.worker import get_worker_stats as _get_worker_stats

        return _get_worker_stats()
    except ImportError:
        logger.debug("spine.execution.worker not available")
        return []
    except Exception:
        logger.exception("Failed to fetch worker stats")
        return []
