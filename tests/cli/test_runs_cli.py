"""Tests for ``spine-core runs`` CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from spine.cli.runs import app

runner = CliRunner()


def _make_paged(items, total):
    from spine.ops.result import PagedResult
    return PagedResult(success=True, data=items, total=total)


def _make_ok(data=None):
    from spine.ops.result import OperationResult
    return OperationResult(success=True, data=data or {})


def _make_error(message="Failed", code="NOT_FOUND"):
    from spine.ops.result import OperationError, OperationResult
    return OperationResult(success=False, error=OperationError(code=code, message=message))


class TestRunsList:
    @patch("spine.ops.runs.list_runs")
    @patch("spine.cli.runs.make_context")
    def test_list_runs_default(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = _make_paged([], 0)

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0

    @patch("spine.ops.runs.list_runs")
    @patch("spine.cli.runs.make_context")
    def test_list_runs_with_filters(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = _make_paged([{"id": "r1", "status": "completed"}], 1)

        result = runner.invoke(app, [
            "list", "--kind", "python", "--status", "completed",
            "--workflow", "etl", "--limit", "10", "--offset", "5",
        ])
        assert result.exit_code == 0

    @patch("spine.ops.runs.list_runs")
    @patch("spine.cli.runs.make_context")
    def test_list_runs_json(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = _make_paged([], 0)

        result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0


class TestRunsShow:
    @patch("spine.ops.runs.get_run")
    @patch("spine.cli.runs.make_context")
    def test_show_run(self, mock_ctx, mock_get):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_get.return_value = _make_ok({"id": "run-123", "status": "completed"})

        result = runner.invoke(app, ["show", "run-123"])
        assert result.exit_code == 0

    @patch("spine.ops.runs.get_run")
    @patch("spine.cli.runs.make_context")
    def test_show_run_json(self, mock_ctx, mock_get):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_get.return_value = _make_ok({"id": "run-123"})

        result = runner.invoke(app, ["show", "run-123", "--json"])
        assert result.exit_code == 0

    @patch("spine.ops.runs.get_run")
    @patch("spine.cli.runs.make_context")
    def test_show_run_error(self, mock_ctx, mock_get):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_get.return_value = _make_error("Run not found")

        result = runner.invoke(app, ["show", "bad-id"])
        assert result.exit_code == 1


class TestRunsCancel:
    @patch("spine.ops.runs.cancel_run")
    @patch("spine.cli.runs.make_context")
    def test_cancel_run(self, mock_ctx, mock_cancel):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_cancel.return_value = _make_ok({"cancelled": True})

        result = runner.invoke(app, ["cancel", "run-123"])
        assert result.exit_code == 0

    @patch("spine.ops.runs.cancel_run")
    @patch("spine.cli.runs.make_context")
    def test_cancel_with_reason(self, mock_ctx, mock_cancel):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_cancel.return_value = _make_ok({"cancelled": True})

        result = runner.invoke(app, ["cancel", "run-123", "--reason", "Timeout"])
        assert result.exit_code == 0


class TestRunsRetry:
    @patch("spine.ops.runs.retry_run")
    @patch("spine.cli.runs.make_context")
    def test_retry_run(self, mock_ctx, mock_retry):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_retry.return_value = _make_ok({"retried": True})

        result = runner.invoke(app, ["retry", "run-123"])
        assert result.exit_code == 0

    @patch("spine.ops.runs.retry_run")
    @patch("spine.cli.runs.make_context")
    def test_retry_run_json(self, mock_ctx, mock_retry):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_retry.return_value = _make_ok({"retried": True})

        result = runner.invoke(app, ["retry", "run-123", "--json"])
        assert result.exit_code == 0
