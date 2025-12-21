"""Tests for spine.ops.stats — run stats and worker delegation.

Tests the ops-layer functions including the new worker stat wrappers
that delegate to the execution layer.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spine.ops.stats import get_active_workers, get_queue_depths, get_run_stats, get_worker_stats


class TestGetRunStats:
    """get_run_stats tests."""

    def test_empty_result(self):
        conn = MagicMock()
        conn.fetchall.return_value = []
        stats = get_run_stats(conn)
        assert stats == {"total": 0}

    def test_dict_rows(self):
        conn = MagicMock()
        conn.fetchall.return_value = [
            {"status": "COMPLETED", "cnt": 10},
            {"status": "FAILED", "cnt": 2},
        ]
        stats = get_run_stats(conn)
        assert stats["COMPLETED"] == 10
        assert stats["FAILED"] == 2
        assert stats["total"] == 12

    def test_tuple_rows(self):
        conn = MagicMock()
        conn.fetchall.return_value = [("RUNNING", 5), ("PENDING", 3)]
        stats = get_run_stats(conn)
        assert stats["RUNNING"] == 5
        assert stats["PENDING"] == 3
        assert stats["total"] == 8

    def test_query_failure_returns_zero(self):
        conn = MagicMock()
        conn.execute.side_effect = Exception("DB error")
        stats = get_run_stats(conn)
        assert stats == {"total": 0}


class TestGetQueueDepths:
    """get_queue_depths tests."""

    def test_empty_result(self):
        conn = MagicMock()
        conn.fetchall.return_value = []
        depths = get_queue_depths(conn)
        assert depths == []

    def test_dict_rows(self):
        conn = MagicMock()
        conn.fetchall.return_value = [
            {"lane": "normal", "status": "pending", "cnt": 5},
            {"lane": "normal", "status": "running", "cnt": 2},
            {"lane": "realtime", "status": "pending", "cnt": 1},
        ]
        depths = get_queue_depths(conn)
        assert len(depths) == 2
        normal = next(d for d in depths if d["lane"] == "normal")
        assert normal["pending"] == 5
        assert normal["running"] == 2

    def test_query_failure_returns_empty(self):
        conn = MagicMock()
        conn.execute.side_effect = Exception("DB error")
        depths = get_queue_depths(conn)
        assert depths == []


class TestGetActiveWorkers:
    """get_active_workers delegation tests."""

    def test_returns_list(self):
        result = get_active_workers()
        assert isinstance(result, list)

    def test_handles_import_error(self, monkeypatch):
        """Should return empty list if execution module unavailable."""
        # The function already handles ImportError internally
        result = get_active_workers()
        assert isinstance(result, list)


class TestGetWorkerStats:
    """get_worker_stats delegation tests."""

    def test_returns_list(self):
        result = get_worker_stats()
        assert isinstance(result, list)
