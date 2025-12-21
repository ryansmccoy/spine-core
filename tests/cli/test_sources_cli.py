"""Tests for ``spine.cli.sources`` CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from spine.cli.sources import app

runner = CliRunner()


def _make_paged(data, total):
    from spine.ops.result import PagedResult
    return PagedResult(success=True, data=data, total=total)


def _make_ok(data=None):
    from spine.ops.result import OperationResult
    return OperationResult(success=True, data=data or {})


def _make_error(message="Failed", code="NOT_FOUND"):
    from spine.ops.result import OperationError, OperationResult
    return OperationResult(success=False, error=OperationError(code=code, message=message))


class TestSourcesList:
    @patch("spine.ops.sources.list_sources")
    @patch("spine.cli.sources.make_context")
    def test_list_default(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = _make_paged([], 0)
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.list_sources")
    @patch("spine.cli.sources.make_context")
    def test_list_with_filters(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = _make_paged([{"id": "s1"}], 1)
        result = runner.invoke(app, ["list", "--type", "file", "--domain", "sec"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.list_sources")
    @patch("spine.cli.sources.make_context")
    def test_list_json(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = _make_paged([], 0)
        result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0


class TestSourcesRegister:
    @patch("spine.ops.sources.register_source")
    @patch("spine.cli.sources.make_context")
    def test_register_default(self, mock_ctx, mock_register):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_register.return_value = _make_ok({"id": "s-new"})
        result = runner.invoke(app, ["register", "test-source"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.register_source")
    @patch("spine.cli.sources.make_context")
    def test_register_with_options(self, mock_ctx, mock_register):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_register.return_value = _make_ok({"id": "s-new"})
        result = runner.invoke(app, [
            "register", "test-source",
            "--type", "api",
            "--domain", "finra",
            "--config", '{"url": "http://example.com"}',
        ])
        assert result.exit_code == 0


class TestSourcesGet:
    @patch("spine.ops.sources.get_source")
    @patch("spine.cli.sources.make_context")
    def test_get_source(self, mock_ctx, mock_get):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_get.return_value = _make_ok({"id": "s1", "name": "test"})
        result = runner.invoke(app, ["get", "s1"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.get_source")
    @patch("spine.cli.sources.make_context")
    def test_get_source_json(self, mock_ctx, mock_get):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_get.return_value = _make_ok({"id": "s1"})
        result = runner.invoke(app, ["get", "s1", "--json"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.get_source")
    @patch("spine.cli.sources.make_context")
    def test_get_source_not_found(self, mock_ctx, mock_get):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_get.return_value = _make_error("Not found")
        result = runner.invoke(app, ["get", "bad"])
        assert result.exit_code == 1


class TestSourcesDelete:
    @patch("spine.ops.sources.delete_source")
    @patch("spine.cli.sources.make_context")
    def test_delete_source(self, mock_ctx, mock_delete):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_delete.return_value = _make_ok({"deleted": True})
        result = runner.invoke(app, ["delete", "s1", "--force"])
        assert result.exit_code == 0


class TestSourcesEnable:
    @patch("spine.ops.sources.enable_source")
    @patch("spine.cli.sources.make_context")
    def test_enable_source(self, mock_ctx, mock_enable):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_enable.return_value = _make_ok({"id": "s1", "enabled": True})
        result = runner.invoke(app, ["enable", "s1"])
        assert result.exit_code == 0
