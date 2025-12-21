"""Tests for ``spine.ops.stats`` — run statistics and queue depths."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.stats import (
    get_active_workers,
    get_queue_depths,
    get_run_history,
    get_run_stats,
    get_worker_stats,
)


class TestGetRunStats:
    def test_dict_rows(self):
        conn = MagicMock()
        conn.fetchall.return_value = [
            {"status": "completed", "cnt": 10},
            {"status": "failed", "cnt": 3},
        ]

        result = get_run_stats(conn)
        assert result["completed"] == 10
        assert result["failed"] == 3
        assert result["total"] == 13

    def test_tuple_rows(self):
        conn = MagicMock()
        conn.fetchall.return_value = [("running", 5)]

        result = get_run_stats(conn)
        assert result["running"] == 5
        assert result["total"] == 5

    def test_row_with_keys(self):
        class RowLike:
            def keys(self):
                return ["status", "cnt"]

            def __iter__(self):
                for k in self.keys():
                    yield k

            def __getitem__(self, k):
                return {"status": "pending", "cnt": 2}[k]

        conn = MagicMock()
        conn.fetchall.return_value = [RowLike()]

        result = get_run_stats(conn)
        assert result["pending"] == 2

    def test_error_returns_empty(self):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError("no table")

        result = get_run_stats(conn)
        assert result == {"total": 0}


class TestGetQueueDepths:
    def test_dict_rows(self):
        conn = MagicMock()
        conn.fetchall.return_value = [
            {"lane": "critical", "status": "pending", "cnt": 5},
            {"lane": "critical", "status": "running", "cnt": 2},
            {"lane": "default", "status": "pending", "cnt": 1},
        ]

        result = get_queue_depths(conn)
        assert len(result) == 2
        crit = next(r for r in result if r["lane"] == "critical")
        assert crit["pending"] == 5
        assert crit["running"] == 2

    def test_tuple_rows(self):
        conn = MagicMock()
        conn.fetchall.return_value = [("fast", "pending", 3)]

        result = get_queue_depths(conn)
        assert result[0]["lane"] == "fast"
        assert result[0]["pending"] == 3

    def test_row_with_keys(self):
        class RowLike:
            def keys(self):
                return ["lane", "status", "cnt"]

            def __iter__(self):
                for k in self.keys():
                    yield k

            def __getitem__(self, k):
                return {"lane": "default", "status": "running", "cnt": 7}[k]

        conn = MagicMock()
        conn.fetchall.return_value = [RowLike()]

        result = get_queue_depths(conn)
        assert result[0]["running"] == 7

    def test_none_lane_defaults(self):
        conn = MagicMock()
        conn.fetchall.return_value = [{"lane": None, "status": "pending", "cnt": 1}]

        result = get_queue_depths(conn)
        assert result[0]["lane"] == "default"

    def test_error_returns_empty(self):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError("no table")

        result = get_queue_depths(conn)
        assert result == []


class TestGetRunHistory:
    def test_empty_database(self):
        conn = MagicMock()
        conn.fetchall.return_value = []

        result = get_run_history(conn, hours=1, buckets=4)
        assert len(result) == 4
        assert all(r["completed"] == 0 for r in result)

    def test_with_rows(self):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        recent = (now - timedelta(minutes=5)).isoformat()

        conn = MagicMock()
        conn.fetchall.return_value = [
            {"status": "completed", "started_at": recent},
            {"status": "failed", "started_at": recent},
        ]

        result = get_run_history(conn, hours=1, buckets=4)
        assert len(result) == 4
        # At least one bucket should have data
        total = sum(r["completed"] + r["failed"] for r in result)
        assert total == 2

    def test_row_tuple_format(self):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        recent = (now - timedelta(minutes=5)).isoformat()

        conn = MagicMock()
        conn.fetchall.return_value = [("completed", recent)]

        result = get_run_history(conn, hours=1, buckets=4)
        total = sum(r["completed"] for r in result)
        assert total == 1

    def test_error_returns_empty_buckets(self):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError("no table")

        result = get_run_history(conn, hours=1, buckets=4)
        assert len(result) == 4

    def test_invalid_timestamp_skips(self):
        conn = MagicMock()
        conn.fetchall.return_value = [{"status": "completed", "started_at": "not-a-date"}]

        result = get_run_history(conn, hours=1, buckets=2)
        total = sum(r["completed"] for r in result)
        assert total == 0

    def test_empty_started_at_skips(self):
        conn = MagicMock()
        conn.fetchall.return_value = [{"status": "completed", "started_at": ""}]

        result = get_run_history(conn, hours=1, buckets=2)
        total = sum(r["completed"] for r in result)
        assert total == 0

    def test_unknown_status_ignored(self):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        recent = (now - timedelta(minutes=5)).isoformat()

        conn = MagicMock()
        conn.fetchall.return_value = [{"status": "unknown_status", "started_at": recent}]

        result = get_run_history(conn, hours=1, buckets=4)
        total = sum(r["completed"] + r["failed"] + r["running"] + r["cancelled"] for r in result)
        assert total == 0


class TestGetActiveWorkers:
    @patch("spine.ops.stats._get_active_workers", create=True)
    def test_success(self, mock_fn):
        # Patch the lazy import
        with patch("spine.execution.worker.get_active_workers", return_value=["w1"]):
            result = get_active_workers()
            assert result == ["w1"]

    def test_import_error(self):
        with patch.dict("sys.modules", {"spine.execution.worker": None}):
            result = get_active_workers()
            assert result == []


class TestGetWorkerStats:
    def test_success(self):
        with patch("spine.execution.worker.get_worker_stats", return_value=[{"id": "w1"}]):
            result = get_worker_stats()
            assert result == [{"id": "w1"}]

    def test_import_error(self):
        with patch.dict("sys.modules", {"spine.execution.worker": None}):
            result = get_worker_stats()
            assert result == []
