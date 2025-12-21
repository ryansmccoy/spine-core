"""Tests for spine.ops.runs — run operations coverage.

Uses MockConnection from conftest and exercises the main ops functions
(list_runs, get_run, cancel_run, retry_run, submit_run, etc.).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext
from spine.ops.requests import (
    CancelRunRequest,
    GetRunRequest,
    ListRunsRequest,
    RetryRunRequest,
    SubmitRunRequest,
)
from spine.ops.runs import cancel_run, get_run, list_runs, retry_run, submit_run


@pytest.fixture
def ctx(mock_conn):
    return OperationContext(conn=mock_conn, caller="test")


@pytest.fixture
def dry_ctx(mock_conn):
    return OperationContext(conn=mock_conn, caller="test", dry_run=True)


@pytest.fixture
def mock_conn():
    """Minimal mock connection."""
    conn = MagicMock()
    conn.execute.return_value = MagicMock(fetchall=MagicMock(return_value=[]))
    conn.commit = MagicMock()
    return conn


# ─── list_runs ───────────────────────────────────────────────────────


class TestListRuns:
    def test_empty_result(self, ctx):
        request = ListRunsRequest(limit=10)
        with patch("spine.ops.runs._query_runs", return_value=([], 0)):
            result = list_runs(ctx, request)
        assert result.success is True
        assert result.total == 0
        assert result.data == []

    def test_with_status_filter(self, ctx):
        request = ListRunsRequest(status="COMPLETED", limit=5)
        with patch("spine.ops.runs._query_runs", return_value=([], 0)):
            result = list_runs(ctx, request)
        assert result.success is True

    def test_internal_error(self, ctx):
        request = ListRunsRequest(limit=10)
        with patch("spine.ops.runs._query_runs", side_effect=Exception("db error")):
            result = list_runs(ctx, request)
        assert result.success is False
        assert "INTERNAL" in (result.error.code if result.error else "")


# ─── get_run ─────────────────────────────────────────────────────────


class TestGetRun:
    def test_missing_run_id(self, ctx):
        request = GetRunRequest(run_id="")
        result = get_run(ctx, request)
        assert result.success is False

    def test_not_found(self, ctx):
        request = GetRunRequest(run_id="run-missing")
        with patch("spine.ops.runs._fetch_run_row", return_value=None):
            result = get_run(ctx, request)
        assert result.success is False
        assert "not found" in (result.error.message if result.error else "").lower()

    def test_found(self, ctx):
        request = GetRunRequest(run_id="run-1")
        mock_row = {
            "run_id": "run-1",
            "kind": "workflow",
            "name": "etl",
            "status": "COMPLETED",
            "params": "{}",
            "result": "{}",
            "error": None,
            "started_at": None,
            "finished_at": None,
            "submitted_at": None,
            "created_at": None,
        }
        with patch("spine.ops.runs._fetch_run_row", return_value=mock_row), \
             patch("spine.ops.runs._row_to_detail") as mock_convert:
            mock_detail = MagicMock()
            mock_detail.run_id = "run-1"
            mock_convert.return_value = mock_detail
            result = get_run(ctx, request)
        assert result.success is True


# ─── cancel_run ──────────────────────────────────────────────────────


class TestCancelRun:
    def test_missing_run_id(self, ctx):
        request = CancelRunRequest(run_id="")
        result = cancel_run(ctx, request)
        assert result.success is False

    def test_dry_run_succeeds(self, dry_ctx):
        request = CancelRunRequest(run_id="run-1")
        result = cancel_run(dry_ctx, request)
        assert result.success is True

    def test_not_found(self, ctx):
        request = CancelRunRequest(run_id="run-missing")
        with patch("spine.ops.runs._exec_repo") as mock_repo:
            mock_repo.return_value.get_by_id.return_value = None
            result = cancel_run(ctx, request)
        assert result.success is False

    def test_terminal_status_rejected(self, ctx):
        request = CancelRunRequest(run_id="run-1")
        with patch("spine.ops.runs._exec_repo") as mock_repo:
            mock_repo.return_value.get_by_id.return_value = {"status": "completed"}
            result = cancel_run(ctx, request)
        assert result.success is False
        assert "terminal" in (result.error.message if result.error else "").lower()

    @patch("spine.core.events.publish_event")
    def test_cancel_success(self, mock_pub, ctx):
        request = CancelRunRequest(run_id="run-1", reason="testing")
        with patch("spine.ops.runs._exec_repo") as mock_repo:
            mock_repo.return_value.get_by_id.return_value = {"status": "running"}
            mock_repo.return_value.update_status = MagicMock()
            mock_repo.return_value.commit = MagicMock()
            result = cancel_run(ctx, request)
        assert result.success is True


# ─── retry_run ───────────────────────────────────────────────────────


class TestRetryRun:
    def test_missing_run_id(self, ctx):
        request = RetryRunRequest(run_id="")
        result = retry_run(ctx, request)
        assert result.success is False

    def test_dry_run_succeeds(self, dry_ctx):
        request = RetryRunRequest(run_id="run-1")
        result = retry_run(dry_ctx, request)
        assert result.success is True


# ─── submit_run ──────────────────────────────────────────────────────


class TestSubmitRun:
    def test_missing_name(self, ctx):
        request = SubmitRunRequest(kind="task", name="")
        result = submit_run(ctx, request)
        assert result.success is False

    def test_dry_run_succeeds(self, dry_ctx):
        request = SubmitRunRequest(kind="task", name="echo")
        result = submit_run(dry_ctx, request)
        assert result.success is True
