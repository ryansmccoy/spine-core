"""Tests for ``spine.ops.runs`` — run submission, query, cancel, retry operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext
from spine.ops.runs import (
    cancel_run,
    get_run,
    get_run_events,
    get_run_logs,
    get_run_steps,
    list_runs,
    retry_run,
    submit_run,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ctx():
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test")


@pytest.fixture()
def dry_ctx():
    conn = MagicMock()
    return OperationContext(conn=conn, caller="test", dry_run=True)


def _run_row(**overrides):
    base = {
        "id": "run_001",
        "name": "daily_ingest",
        "workflow_name": "ingest_wf",
        "status": "completed",
        "kind": "operation",
        "priority": "normal",
        "params": None,
        "result": None,
        "error": None,
        "error_type": None,
        "parent_run_id": None,
        "correlation_id": None,
        "idempotency_key": None,
        "attempt": 1,
        "max_retries": 3,
        "executor": "memory",
        "external_ref": None,
        "tags": None,
        "metadata": None,
        "created_at": "2026-01-01T00:00:00",
        "started_at": "2026-01-01T00:00:01",
        "completed_at": "2026-01-01T00:00:05",
        "updated_at": "2026-01-01T00:00:05",
        "duration_ms": 4000,
        "created_by": "test",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# list_runs
# ---------------------------------------------------------------------------

class TestListRuns:
    @patch("spine.ops.runs._exec_repo")
    def test_list_returns_paged(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_executions.return_value = ([_run_row()], 1)
        mock_repo_factory.return_value = repo

        from spine.ops.runs import ListRunsRequest
        result = list_runs(ctx, ListRunsRequest())
        assert result.success is True
        assert result.total == 1

    @patch("spine.ops.runs._exec_repo")
    def test_list_empty(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_executions.return_value = ([], 0)
        mock_repo_factory.return_value = repo

        from spine.ops.runs import ListRunsRequest
        result = list_runs(ctx, ListRunsRequest())
        assert result.total == 0

    @patch("spine.ops.runs._exec_repo")
    def test_list_handles_exception(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_executions.side_effect = Exception("DB unavailable")
        mock_repo_factory.return_value = repo

        from spine.ops.runs import ListRunsRequest
        result = list_runs(ctx, ListRunsRequest())
        assert result.success is False


# ---------------------------------------------------------------------------
# get_run
# ---------------------------------------------------------------------------

class TestGetRun:
    @patch("spine.ops.runs._exec_repo")
    def test_get_existing(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.get_by_id.return_value = _run_row()
        mock_repo_factory.return_value = repo

        from spine.ops.runs import GetRunRequest
        result = get_run(ctx, GetRunRequest(run_id="run_001"))
        assert result.success is True

    @patch("spine.ops.runs._exec_repo")
    def test_get_not_found(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.get_by_id.return_value = None
        mock_repo_factory.return_value = repo

        from spine.ops.runs import GetRunRequest
        result = get_run(ctx, GetRunRequest(run_id="run_missing"))
        assert result.success is False

    def test_get_empty_run_id(self, ctx):
        from spine.ops.runs import GetRunRequest
        result = get_run(ctx, GetRunRequest(run_id=""))
        assert result.success is False


# ---------------------------------------------------------------------------
# submit_run
# ---------------------------------------------------------------------------

class TestSubmitRun:
    @patch("spine.ops.runs._exec_repo")
    def test_submit_success(self, mock_repo_factory, ctx):
        repo = MagicMock()
        mock_repo_factory.return_value = repo

        from spine.ops.runs import SubmitRunRequest
        result = submit_run(ctx, SubmitRunRequest(
            name="test_operation",
            kind="operation",
        ))
        assert result.success is True
        repo.create_execution.assert_called_once()

    @patch("spine.ops.runs._exec_repo")
    def test_submit_handles_exception(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.create_execution.side_effect = Exception("DB error")
        mock_repo_factory.return_value = repo

        from spine.ops.runs import SubmitRunRequest
        result = submit_run(ctx, SubmitRunRequest(name="err", kind="operation"))
        assert result.success is False

    def test_submit_dry_run(self, dry_ctx):
        from spine.ops.runs import SubmitRunRequest
        result = submit_run(dry_ctx, SubmitRunRequest(name="checking", kind="task"))
        assert result.success is True


# ---------------------------------------------------------------------------
# cancel_run
# ---------------------------------------------------------------------------

class TestCancelRun:
    @patch("spine.ops.runs._exec_repo")
    def test_cancel_success(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.get_by_id.return_value = _run_row(status="running")
        mock_repo_factory.return_value = repo

        from spine.ops.runs import CancelRunRequest
        result = cancel_run(ctx, CancelRunRequest(run_id="run_001"))
        assert result.success is True
        repo.update_status.assert_called_once()

    def test_cancel_empty_run_id(self, ctx):
        from spine.ops.runs import CancelRunRequest
        result = cancel_run(ctx, CancelRunRequest(run_id=""))
        assert result.success is False

    def test_cancel_dry_run(self, dry_ctx):
        from spine.ops.runs import CancelRunRequest
        result = cancel_run(dry_ctx, CancelRunRequest(run_id="run_001"))
        assert result.success is True


# ---------------------------------------------------------------------------
# retry_run
# ---------------------------------------------------------------------------

class TestRetryRun:
    @patch("spine.ops.runs._exec_repo")
    def test_retry_success(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.get_by_id.return_value = _run_row(status="failed")
        mock_repo_factory.return_value = repo

        from spine.ops.runs import RetryRunRequest
        result = retry_run(ctx, RetryRunRequest(run_id="run_001"))
        assert result.success is True

    @patch("spine.ops.runs._exec_repo")
    def test_retry_not_found(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.get_by_id.return_value = None
        mock_repo_factory.return_value = repo

        from spine.ops.runs import RetryRunRequest
        result = retry_run(ctx, RetryRunRequest(run_id="run_xxx"))
        assert result.success is False

    def test_retry_empty_run_id(self, ctx):
        from spine.ops.runs import RetryRunRequest
        result = retry_run(ctx, RetryRunRequest(run_id=""))
        assert result.success is False


# ---------------------------------------------------------------------------
# get_run_events / logs / steps
# ---------------------------------------------------------------------------

class TestRunSubResources:
    @patch("spine.ops.runs._exec_repo")
    def test_get_run_events(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_events.return_value = ([], 0)
        mock_repo_factory.return_value = repo

        from spine.ops.runs import GetRunEventsRequest
        result = get_run_events(ctx, GetRunEventsRequest(run_id="run_001"))
        assert result.success is True

    def test_get_run_events_empty_id(self, ctx):
        from spine.ops.runs import GetRunEventsRequest
        result = get_run_events(ctx, GetRunEventsRequest(run_id=""))
        assert result.success is False

    @patch("spine.ops.runs._exec_repo")
    def test_get_run_logs(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_logs.return_value = ([], 0)
        mock_repo_factory.return_value = repo
        # get_run_logs also uses ctx.conn for count query
        ctx.conn.fetchone.return_value = (0,)

        from spine.ops.runs import GetRunLogsRequest
        result = get_run_logs(ctx, GetRunLogsRequest(run_id="run_001"))
        assert result.success is True

    @patch("spine.ops.runs._wf_repo")
    def test_get_run_steps(self, mock_wf_repo_factory, ctx):
        wf_repo = MagicMock()
        wf_repo.list_steps.return_value = ([], 0)
        mock_wf_repo_factory.return_value = wf_repo

        from spine.ops.runs import GetRunStepsRequest
        result = get_run_steps(ctx, GetRunStepsRequest(run_id="run_001"))
        assert result.success is True

    def test_get_run_steps_empty_id(self, ctx):
        from spine.ops.runs import GetRunStepsRequest
        result = get_run_steps(ctx, GetRunStepsRequest(run_id=""))
        assert result.success is False
