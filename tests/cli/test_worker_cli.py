"""Tests for ``spine-core worker`` CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from spine.cli.worker import app

runner = CliRunner()


class TestWorkerStart:
    @patch("spine.execution.worker.WorkerLoop")
    def test_start_defaults(self, mock_cls):
        loop = MagicMock()
        mock_cls.return_value = loop

        result = runner.invoke(app, ["start"])
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            db_path="spine.db",
            poll_interval=2.0,
            batch_size=10,
            max_workers=4,
            worker_id=None,
        )
        loop.start.assert_called_once()

    @patch("spine.execution.worker.WorkerLoop")
    def test_start_custom_params(self, mock_cls):
        loop = MagicMock()
        mock_cls.return_value = loop

        result = runner.invoke(app, [
            "start",
            "--db", "/tmp/test.db",
            "--workers", "8",
            "--poll-interval", "5.0",
            "--batch-size", "20",
            "--id", "worker-1",
        ])
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            db_path="/tmp/test.db",
            poll_interval=5.0,
            batch_size=20,
            max_workers=8,
            worker_id="worker-1",
        )

    @patch("spine.execution.worker.WorkerLoop")
    def test_start_keyboard_interrupt(self, mock_cls):
        loop = MagicMock()
        loop.start.side_effect = KeyboardInterrupt()
        mock_cls.return_value = loop

        result = runner.invoke(app, ["start"])
        assert result.exit_code == 0

    @patch("spine.execution.worker.WorkerLoop")
    def test_start_error(self, mock_cls):
        loop = MagicMock()
        loop.start.side_effect = RuntimeError("DB locked")
        mock_cls.return_value = loop

        result = runner.invoke(app, ["start"])
        assert result.exit_code == 1


class TestWorkerStatus:
    @patch("spine.execution.worker.get_active_workers")
    def test_status_no_workers(self, mock_get):
        mock_get.return_value = []

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "No active" in result.output

    @patch("spine.execution.worker.get_active_workers")
    def test_status_with_workers(self, mock_get):
        w = MagicMock()
        w.worker_id = "w-1"
        w.pid = 12345
        w.status = "running"
        w.runs_processed = 50
        w.runs_failed = 2
        mock_get.return_value = [w]

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "w-1" in result.output
        assert "12345" in result.output
