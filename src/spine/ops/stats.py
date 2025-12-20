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
