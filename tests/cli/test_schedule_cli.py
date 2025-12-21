"""Tests for ``spine-core schedule`` CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from spine.cli.schedule import app

runner = CliRunner()


def _make_paged(items, total):
    from spine.ops.result import PagedResult
    return PagedResult(success=True, data=items, total=total)


def _make_ok(data=None):
    from spine.ops.result import OperationResult
    return OperationResult(success=True, data=data or {})


class TestScheduleList:
    @patch("spine.ops.schedules.list_schedules")
    @patch("spine.cli.schedule.make_context")
    def test_list_schedules(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = _make_paged([], 0)

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0

    @patch("spine.ops.schedules.list_schedules")
    @patch("spine.cli.schedule.make_context")
    def test_list_schedules_json(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = _make_paged([{"id": "s1", "cron": "0 * * * *"}], 1)

        result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0


class TestScheduleShow:
    @patch("spine.ops.schedules.get_schedule")
    @patch("spine.cli.schedule.make_context")
    def test_show_schedule(self, mock_ctx, mock_get):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_get.return_value = _make_ok({"id": "s1", "cron": "0 * * * *"})

        result = runner.invoke(app, ["show", "s1"])
        assert result.exit_code == 0

    @patch("spine.ops.schedules.get_schedule")
    @patch("spine.cli.schedule.make_context")
    def test_show_schedule_json(self, mock_ctx, mock_get):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_get.return_value = _make_ok({"id": "s1"})

        result = runner.invoke(app, ["show", "s1", "--json"])
        assert result.exit_code == 0


class TestScheduleCreate:
    @patch("spine.ops.schedules.create_schedule")
    @patch("spine.cli.schedule.make_context")
    def test_create_schedule_cron(self, mock_ctx, mock_create):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_create.return_value = _make_ok({"id": "s-new"})

        result = runner.invoke(app, ["create", "my-workflow", "--cron", "0 * * * *"])
        assert result.exit_code == 0

    @patch("spine.ops.schedules.create_schedule")
    @patch("spine.cli.schedule.make_context")
    def test_create_schedule_interval(self, mock_ctx, mock_create):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_create.return_value = _make_ok({"id": "s-new"})

        result = runner.invoke(app, ["create", "my-workflow", "--interval", "300"])
        assert result.exit_code == 0

    @patch("spine.ops.schedules.create_schedule")
    @patch("spine.cli.schedule.make_context")
    def test_create_disabled(self, mock_ctx, mock_create):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_create.return_value = _make_ok({"id": "s-new", "enabled": False})

        result = runner.invoke(app, ["create", "my-workflow", "--disabled"])
        assert result.exit_code == 0


class TestScheduleUpdate:
    @patch("spine.ops.schedules.update_schedule")
    @patch("spine.cli.schedule.make_context")
    def test_update_schedule(self, mock_ctx, mock_update):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_update.return_value = _make_ok({"id": "s1"})

        result = runner.invoke(app, ["update", "s1", "--cron", "*/5 * * * *"])
        assert result.exit_code == 0

    @patch("spine.ops.schedules.update_schedule")
    @patch("spine.cli.schedule.make_context")
    def test_update_schedule_disable(self, mock_ctx, mock_update):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_update.return_value = _make_ok({"id": "s1", "enabled": False})

        result = runner.invoke(app, ["update", "s1", "--disabled"])
        assert result.exit_code == 0


class TestScheduleDelete:
    @patch("spine.ops.schedules.delete_schedule")
    @patch("spine.cli.schedule.make_context")
    def test_delete_schedule(self, mock_ctx, mock_delete):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_delete.return_value = _make_ok({"deleted": True})

        result = runner.invoke(app, ["delete", "s1"])
        assert result.exit_code == 0

    @patch("spine.ops.schedules.delete_schedule")
    @patch("spine.cli.schedule.make_context")
    def test_delete_schedule_json(self, mock_ctx, mock_delete):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_delete.return_value = _make_ok({"deleted": True})

        result = runner.invoke(app, ["delete", "s1", "--json"])
        assert result.exit_code == 0
