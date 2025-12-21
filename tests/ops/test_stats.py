"""Tests for ``spine.ops.stats`` — run stats, queue depths, run history, worker stats."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from spine.ops.stats import (
    get_active_workers,
    get_queue_depths,
    get_run_history,
    get_run_stats,
    get_worker_stats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conn_returning(rows):
    """Create a mock connection whose execute().fetchall() returns *rows*."""
    mock = MagicMock()
    mock.fetchall.return_value = rows
    mock.execute.return_value = None        # execute returns nothing
    # For some code paths, conn.execute returns cursor; for others, conn is cursor.
    # ops.stats calls conn.execute() then conn.fetchall() on the *same* object.
    return mock


def _dict_rows(*tuples):
    """Helper: return list of dicts with expected column names."""
    return [{"status": s, "cnt": c} for s, c in tuples]


# ---------------------------------------------------------------------------
# get_run_stats
# ---------------------------------------------------------------------------


class TestGetRunStats:
    def test_returns_counts_by_status(self):
        conn = _conn_returning(_dict_rows(("completed", 10), ("failed", 3)))
        result = get_run_stats(conn)
        assert result["completed"] == 10
        assert result["failed"] == 3
        assert result["total"] == 13

    def test_empty_table(self):
        conn = _conn_returning([])
        result = get_run_stats(conn)
        assert result == {"total": 0}

    def test_handles_tuple_rows(self):
        conn = _conn_returning([("completed", 5), ("running", 2)])
        result = get_run_stats(conn)
        assert result["completed"] == 5
        assert result["running"] == 2
        assert result["total"] == 7

    def test_query_failure_returns_zero(self):
        conn = MagicMock()
        conn.execute.side_effect = Exception("DB down")
        result = get_run_stats(conn)
        assert result == {"total": 0}


# ---------------------------------------------------------------------------
# get_queue_depths
# ---------------------------------------------------------------------------


class TestGetQueueDepths:
    def test_returns_lane_breakdown(self):
        rows = [
            {"lane": "default", "status": "pending", "cnt": 5},
            {"lane": "default", "status": "running", "cnt": 2},
            {"lane": "gpu", "status": "pending", "cnt": 1},
        ]
        conn = _conn_returning(rows)
        result = get_queue_depths(conn)
        assert any(d["lane"] == "default" and d["pending"] == 5 for d in result)
        assert any(d["lane"] == "gpu" and d["pending"] == 1 for d in result)

    def test_empty_returns_empty_list(self):
        conn = _conn_returning([])
        assert get_queue_depths(conn) == []

    def test_tuple_rows(self):
        conn = _conn_returning([("default", "pending", 3)])
        result = get_queue_depths(conn)
        assert len(result) == 1
        assert result[0]["pending"] == 3

    def test_query_failure_returns_empty(self):
        conn = MagicMock()
        conn.execute.side_effect = Exception("DB unavailable")
        assert get_queue_depths(conn) == []


# ---------------------------------------------------------------------------
# get_run_history
# ---------------------------------------------------------------------------


class TestGetRunHistory:
    def test_returns_expected_buckets(self):
        conn = _conn_returning([])
        result = get_run_history(conn, hours=24, buckets=24)
        assert len(result) == 24
        assert all("completed" in b and "failed" in b for b in result)

    def test_rows_placed_in_correct_bucket(self):
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(hours=1)).isoformat()
        conn = _conn_returning([{"status": "completed", "started_at": ts}])
        result = get_run_history(conn, hours=24, buckets=24)
        total_completed = sum(b["completed"] for b in result)
        assert total_completed == 1

    def test_handles_tuple_rows(self):
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(hours=2)).isoformat()
        conn = _conn_returning([("failed", ts)])
        result = get_run_history(conn, hours=24, buckets=24)
        total_failed = sum(b["failed"] for b in result)
        assert total_failed == 1

    def test_query_failure_returns_empty_buckets(self):
        conn = MagicMock()
        conn.execute.side_effect = Exception("DB down")
        result = get_run_history(conn, hours=24, buckets=4)
        assert len(result) == 4
        assert all(b["completed"] == 0 for b in result)

    def test_invalid_timestamp_skipped(self):
        conn = _conn_returning([{"status": "completed", "started_at": "not-a-date"}])
        result = get_run_history(conn, hours=24, buckets=4)
        total = sum(b["completed"] for b in result)
        assert total == 0


# ---------------------------------------------------------------------------
# Worker stubs (delegation to spine.execution.worker)
# ---------------------------------------------------------------------------


class TestWorkerDelegation:
    def test_get_active_workers_returns_list(self):
        # May return [] if spine.execution.worker not available
        result = get_active_workers()
        assert isinstance(result, list)

    def test_get_worker_stats_returns_list(self):
        result = get_worker_stats()
        assert isinstance(result, list)
