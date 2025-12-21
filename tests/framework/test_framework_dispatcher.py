"""Tests for spine.framework.dispatcher — Basic-tier operation dispatcher.

Covers Execution, TriggerSource, Lane enums, OperationDispatcher submit/query,
and error-handling paths (OperationNotFoundError, BadParamsError, generic Exception).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from spine.framework.dispatcher import (
    Execution,
    Lane,
    OperationDispatcher,
    TriggerSource,
)
from spine.framework.exceptions import BadParamsError, OperationNotFoundError
from spine.framework.operations import OperationResult, OperationStatus


# ── Enum tests ──────────────────────────────────────────────────────


class TestEnums:
    def test_trigger_source_values(self):
        assert TriggerSource.CLI.value == "cli"
        assert TriggerSource.API.value == "api"
        assert TriggerSource.SCHEDULER.value == "scheduler"
        assert TriggerSource.RETRY.value == "retry"
        assert TriggerSource.MANUAL.value == "manual"

    def test_lane_values(self):
        assert Lane.NORMAL.value == "normal"
        assert Lane.BACKFILL.value == "backfill"
        assert Lane.SLOW.value == "slow"


# ── Execution dataclass ────────────────────────────────────────────


class TestExecution:
    def test_creation(self):
        e = Execution(
            id="ex-1",
            operation="test_pipe",
            params={"ticker": "AAPL"},
            lane=Lane.NORMAL,
            trigger_source=TriggerSource.CLI,
            logical_key=None,
            status=OperationStatus.PENDING,
            created_at=datetime.now(),
        )
        assert e.id == "ex-1"
        assert e.started_at is None
        assert e.completed_at is None
        assert e.error is None
        assert e.result is None


# ── OperationDispatcher ─────────────────────────────────────────────


class TestOperationDispatcher:
    @patch("spine.framework.dispatcher.get_runner")
    def test_submit_success(self, mock_get_runner):
        result = MagicMock(spec=OperationResult)
        result.status = OperationStatus.COMPLETED
        result.completed_at = datetime.now()
        result.error = None
        result.duration_seconds = 1.5
        result.metrics = {"rows": 100}

        runner = MagicMock()
        runner.run.return_value = result
        mock_get_runner.return_value = runner

        disp = OperationDispatcher()
        exec_ = disp.submit("test_pipe", {"ticker": "AAPL"})

        assert exec_.status == OperationStatus.COMPLETED
        assert exec_.operation == "test_pipe"
        assert exec_.error is None
        runner.run.assert_called_once_with("test_pipe", {"ticker": "AAPL"})

    @patch("spine.framework.dispatcher.get_runner")
    def test_submit_failed_result(self, mock_get_runner):
        result = MagicMock(spec=OperationResult)
        result.status = OperationStatus.FAILED
        result.completed_at = datetime.now()
        result.error = "data issue"
        result.duration_seconds = 0.5
        result.metrics = {}

        runner = MagicMock()
        runner.run.return_value = result
        mock_get_runner.return_value = runner

        disp = OperationDispatcher()
        exec_ = disp.submit("bad_pipe")

        assert exec_.status == OperationStatus.FAILED
        assert exec_.error == "data issue"

    @patch("spine.framework.dispatcher.get_runner")
    def test_submit_operation_not_found(self, mock_get_runner):
        runner = MagicMock()
        runner.run.side_effect = OperationNotFoundError("no_pipe")
        mock_get_runner.return_value = runner

        disp = OperationDispatcher()
        with pytest.raises(OperationNotFoundError):
            disp.submit("no_pipe")

    @patch("spine.framework.dispatcher.get_runner")
    def test_submit_bad_params(self, mock_get_runner):
        runner = MagicMock()
        runner.run.side_effect = BadParamsError(
            "bad params", missing_params=["ticker"], invalid_params=[],
        )
        mock_get_runner.return_value = runner

        disp = OperationDispatcher()
        with pytest.raises(BadParamsError):
            disp.submit("pipe", {"wrong": "param"})

    @patch("spine.framework.dispatcher.get_runner")
    def test_submit_unexpected_exception(self, mock_get_runner):
        runner = MagicMock()
        runner.run.side_effect = RuntimeError("unexpected crash")
        mock_get_runner.return_value = runner

        disp = OperationDispatcher()
        exec_ = disp.submit("pipe")

        assert exec_.status == OperationStatus.FAILED
        assert "unexpected crash" in exec_.error

    @patch("spine.framework.dispatcher.get_runner")
    def test_submit_with_lane_and_trigger(self, mock_get_runner):
        result = MagicMock(spec=OperationResult)
        result.status = OperationStatus.COMPLETED
        result.completed_at = datetime.now()
        result.error = None
        result.duration_seconds = 0.1
        result.metrics = None

        runner = MagicMock()
        runner.run.return_value = result
        mock_get_runner.return_value = runner

        disp = OperationDispatcher()
        exec_ = disp.submit(
            "pipe", lane=Lane.BACKFILL, trigger_source=TriggerSource.SCHEDULER,
        )

        assert exec_.lane == Lane.BACKFILL
        assert exec_.trigger_source == TriggerSource.SCHEDULER

    @patch("spine.framework.dispatcher.get_runner")
    def test_get_execution(self, mock_get_runner):
        result = MagicMock(spec=OperationResult)
        result.status = OperationStatus.COMPLETED
        result.completed_at = datetime.now()
        result.error = None
        result.duration_seconds = 0.1
        result.metrics = {}

        runner = MagicMock()
        runner.run.return_value = result
        mock_get_runner.return_value = runner

        disp = OperationDispatcher()
        exec_ = disp.submit("pipe")

        found = disp.get_execution(exec_.id)
        assert found is exec_

    @patch("spine.framework.dispatcher.get_runner")
    def test_get_execution_not_found(self, mock_get_runner):
        mock_get_runner.return_value = MagicMock()
        disp = OperationDispatcher()
        assert disp.get_execution("nonexistent") is None

    @patch("spine.framework.dispatcher.get_runner")
    def test_list_executions_empty(self, mock_get_runner):
        mock_get_runner.return_value = MagicMock()
        disp = OperationDispatcher()
        assert disp.list_executions() == []

    @patch("spine.framework.dispatcher.get_runner")
    def test_list_executions_filter_by_operation(self, mock_get_runner):
        result = MagicMock(spec=OperationResult)
        result.status = OperationStatus.COMPLETED
        result.completed_at = datetime.now()
        result.error = None
        result.duration_seconds = 0.1
        result.metrics = {}

        runner = MagicMock()
        runner.run.return_value = result
        mock_get_runner.return_value = runner

        disp = OperationDispatcher()
        disp.submit("pipe_a")
        disp.submit("pipe_b")

        results = disp.list_executions(operation="pipe_a")
        assert len(results) == 1
        assert results[0].operation == "pipe_a"

    @patch("spine.framework.dispatcher.get_runner")
    def test_list_executions_filter_by_status(self, mock_get_runner):
        result = MagicMock(spec=OperationResult)
        result.status = OperationStatus.COMPLETED
        result.completed_at = datetime.now()
        result.error = None
        result.duration_seconds = 0.1
        result.metrics = {}

        runner = MagicMock()
        runner.run.return_value = result
        mock_get_runner.return_value = runner

        disp = OperationDispatcher()
        disp.submit("pipe")

        found = disp.list_executions(status=OperationStatus.COMPLETED)
        assert len(found) == 1

        missing = disp.list_executions(status=OperationStatus.PENDING)
        assert len(missing) == 0

    @patch("spine.framework.dispatcher.get_runner")
    def test_list_executions_limit(self, mock_get_runner):
        result = MagicMock(spec=OperationResult)
        result.status = OperationStatus.COMPLETED
        result.completed_at = datetime.now()
        result.error = None
        result.duration_seconds = 0.1
        result.metrics = {}

        runner = MagicMock()
        runner.run.return_value = result
        mock_get_runner.return_value = runner

        disp = OperationDispatcher()
        for _ in range(5):
            disp.submit("pipe")

        results = disp.list_executions(limit=3)
        assert len(results) == 3
