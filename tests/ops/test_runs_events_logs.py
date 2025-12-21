"""Extended tests for spine.ops.runs — event, step, and log operations.

Covers get_run_events, get_run_steps, get_run_logs and internal helpers
(_row_to_summary, _row_to_detail, _row_to_log_entry, _err).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext
from spine.ops.requests import (
    GetRunEventsRequest,
    GetRunLogsRequest,
    GetRunStepsRequest,
)
from spine.ops.runs import (
    _err,
    _row_to_detail,
    _row_to_summary,
    get_run_events,
    get_run_logs,
    get_run_steps,
)


@pytest.fixture
def ctx():
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test")


# ─── _row_to_summary ─────────────────────────────────────────────────


class TestRowToSummary:
    def test_full_row(self):
        row = {
            "id": "run-1",
            "workflow": "daily_etl",
            "status": "completed",
            "started_at": "2024-01-01T00:00:00",
            "finished_at": "2024-01-01T00:05:00",
            "duration_ms": 300000,
        }
        s = _row_to_summary(row)
        assert s.run_id == "run-1"
        assert s.workflow == "daily_etl"
        assert s.status == "completed"
        assert s.duration_ms == 300000

    def test_empty_row(self):
        s = _row_to_summary({})
        assert s.run_id == ""
        assert s.status == ""


# ─── _row_to_detail ──────────────────────────────────────────────────


class TestRowToDetail:
    def test_full_row(self):
        row = {
            "id": "run-1",
            "workflow": "daily_etl",
            "status": "completed",
            "params": {"key": "val"},
            "result": {"output": 42},
            "error": None,
            "started_at": "2024-01-01T00:00:00",
            "finished_at": "2024-01-01T00:05:00",
            "duration_ms": 300000,
        }
        d = _row_to_detail(row)
        assert d.run_id == "run-1"
        assert d.params == {"key": "val"}
        assert d.result == {"output": 42}

    def test_non_dict_params(self):
        row = {"id": "r1", "status": "failed", "params": "not-a-dict", "result": "nope"}
        d = _row_to_detail(row)
        assert d.params == {}
        assert d.result is None


# ─── _err helper ─────────────────────────────────────────────────────


class TestErrHelper:
    def test_creates_operation_error(self):
        e = _err("NOT_FOUND", "Run xyz not found")
        assert e.code == "NOT_FOUND"
        assert "xyz" in e.message


# ─── get_run_events ──────────────────────────────────────────────────


class TestGetRunEvents:
    def test_missing_run_id(self, ctx):
        req = GetRunEventsRequest(run_id="", limit=10, offset=0)
        result = get_run_events(ctx, req)
        assert result.success is False
        assert "VALIDATION" in result.error.code

    @patch("spine.ops.runs._exec_repo")
    def test_returns_events(self, mock_repo, ctx):
        repo = mock_repo.return_value
        repo.list_events.return_value = (
            [
                {"id": "ev-1", "execution_id": "run-1", "event_type": "started", "timestamp": "2024-01-01"},
                {"id": "ev-2", "execution_id": "run-1", "event_type": "completed", "timestamp": "2024-01-01"},
            ],
            2,
        )
        req = GetRunEventsRequest(run_id="run-1", limit=50, offset=0)
        result = get_run_events(ctx, req)
        assert result.success is True
        assert result.total == 2
        assert result.data[0].event_type == "started"

    @patch("spine.ops.runs._exec_repo")
    def test_exception(self, mock_repo, ctx):
        repo = mock_repo.return_value
        repo.list_events.side_effect = RuntimeError("db error")
        req = GetRunEventsRequest(run_id="run-1", limit=10, offset=0)
        result = get_run_events(ctx, req)
        assert result.success is False


# ─── get_run_steps ───────────────────────────────────────────────────


class TestGetRunSteps:
    def test_missing_run_id(self, ctx):
        req = GetRunStepsRequest(run_id="", limit=10, offset=0)
        result = get_run_steps(ctx, req)
        assert result.success is False

    @patch("spine.ops.runs._wf_repo")
    def test_returns_steps(self, mock_repo, ctx):
        repo = mock_repo.return_value
        repo.list_steps.return_value = (
            [
                {
                    "step_id": "s1",
                    "run_id": "run-1",
                    "step_name": "extract",
                    "step_type": "task",
                    "step_order": 1,
                    "status": "completed",
                    "started_at": "2024-01-01T00:00:00",
                    "completed_at": "2024-01-01T00:01:00",
                    "duration_ms": 60000,
                    "metrics": '{"rows": 1000}',
                },
            ],
            1,
        )
        req = GetRunStepsRequest(run_id="run-1", limit=50, offset=0)
        result = get_run_steps(ctx, req)
        assert result.success is True
        assert result.total == 1
        assert result.data[0].step_name == "extract"
        assert result.data[0].metrics == {"rows": 1000}

    @patch("spine.ops.runs._wf_repo")
    def test_dict_metrics(self, mock_repo, ctx):
        repo = mock_repo.return_value
        repo.list_steps.return_value = (
            [{"step_id": "s1", "step_name": "t", "step_type": "task",
              "status": "done", "metrics": {"already": "dict"}}],
            1,
        )
        req = GetRunStepsRequest(run_id="run-1", limit=10, offset=0)
        result = get_run_steps(ctx, req)
        assert result.data[0].metrics == {"already": "dict"}

    @patch("spine.ops.runs._wf_repo")
    def test_bad_json_metrics(self, mock_repo, ctx):
        repo = mock_repo.return_value
        repo.list_steps.return_value = (
            [{"step_id": "s1", "step_name": "t", "step_type": "task",
              "status": "done", "metrics": "not-json{"}],
            1,
        )
        req = GetRunStepsRequest(run_id="run-1", limit=10, offset=0)
        result = get_run_steps(ctx, req)
        assert result.data[0].metrics == {}

    @patch("spine.ops.runs._wf_repo")
    def test_exception(self, mock_repo, ctx):
        repo = mock_repo.return_value
        repo.list_steps.side_effect = RuntimeError("db error")
        req = GetRunStepsRequest(run_id="run-1", limit=10, offset=0)
        result = get_run_steps(ctx, req)
        assert result.success is False


# ─── get_run_logs ────────────────────────────────────────────────────


class TestGetRunLogs:
    def test_missing_run_id(self, ctx):
        req = GetRunLogsRequest(run_id="", limit=10, offset=0)
        result = get_run_logs(ctx, req)
        assert result.success is False
        assert "VALIDATION" in result.error.code

    @patch("spine.ops.runs._query_run_logs")
    @patch("spine.ops.runs._fetch_run_row")
    def test_run_not_found(self, mock_fetch, mock_logs, ctx):
        mock_fetch.return_value = None
        req = GetRunLogsRequest(run_id="missing", limit=10, offset=0)
        result = get_run_logs(ctx, req)
        assert result.success is False
        assert "NOT_FOUND" in result.error.code

    @patch("spine.ops.runs._query_run_logs")
    @patch("spine.ops.runs._fetch_run_row")
    def test_returns_logs(self, mock_fetch, mock_logs, ctx):
        mock_fetch.return_value = {"id": "run-1", "status": "completed"}
        mock_logs.return_value = (
            [
                {"timestamp": "2024-01-01", "level": "INFO", "message": "Starting"},
                {"timestamp": "2024-01-01", "level": "ERROR", "message": "Failed"},
            ],
            2,
        )
        req = GetRunLogsRequest(run_id="run-1", limit=50, offset=0)
        result = get_run_logs(ctx, req)
        assert result.success is True
        assert result.total == 2
        assert result.data[0].level == "INFO"

    @patch("spine.ops.runs._fetch_run_row")
    def test_exception(self, mock_fetch, ctx):
        mock_fetch.side_effect = RuntimeError("db error")
        req = GetRunLogsRequest(run_id="run-1", limit=10, offset=0)
        result = get_run_logs(ctx, req)
        assert result.success is False
