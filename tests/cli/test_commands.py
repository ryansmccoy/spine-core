"""
Tests for CLI app structure and sub-commands.
"""

from __future__ import annotations

import pytest

from typer.testing import CliRunner

from spine.cli.app import app

runner = CliRunner()


class TestRootApp:
    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "spine-core" in result.output

    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        # Should contain version string
        assert "spine-core" in result.output or "0.3" in result.output

    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        # Typer returns exit code 0 or 2 for no_args_is_help
        assert result.exit_code in (0, 2)


class TestSubcommandRegistration:
    """Verify all sub-command groups are registered."""

    def test_db_help(self):
        result = runner.invoke(app, ["db", "--help"])
        assert result.exit_code == 0
        assert "init" in result.output

    def test_workflow_help(self):
        result = runner.invoke(app, ["workflow", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output

    def test_runs_help(self):
        result = runner.invoke(app, ["runs", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output

    def test_schedule_help(self):
        result = runner.invoke(app, ["schedule", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output

    def test_health_help(self):
        result = runner.invoke(app, ["health", "--help"])
        assert result.exit_code == 0

    def test_dlq_help(self):
        result = runner.invoke(app, ["dlq", "--help"])
        assert result.exit_code == 0

    def test_anomaly_help(self):
        result = runner.invoke(app, ["anomaly", "--help"])
        assert result.exit_code == 0

    def test_quality_help(self):
        result = runner.invoke(app, ["quality", "--help"])
        assert result.exit_code == 0

    def test_serve_help(self):
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0


class TestDBCommands:
    def test_init(self, tmp_path):
        db = str(tmp_path / "test.db")
        result = runner.invoke(app, ["db", "init", "--database", db])
        assert result.exit_code == 0

    def test_health(self, tmp_path):
        db = str(tmp_path / "test.db")
        # Init first
        runner.invoke(app, ["db", "init", "--database", db])
        result = runner.invoke(app, ["db", "health", "--database", db])
        assert result.exit_code == 0

    def test_tables(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner.invoke(app, ["db", "init", "--database", db])
        result = runner.invoke(app, ["db", "tables", "--database", db])
        assert result.exit_code == 0

    def test_init_json(self, tmp_path):
        db = str(tmp_path / "test.db")
        result = runner.invoke(app, ["db", "init", "--database", db, "--json"])
        assert result.exit_code == 0


class TestWorkflowCommands:
    def test_list(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner.invoke(app, ["db", "init", "--database", db])
        result = runner.invoke(app, ["workflow", "list", "--database", db])
        assert result.exit_code == 0


class TestRunCommands:
    def test_list(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner.invoke(app, ["db", "init", "--database", db])
        result = runner.invoke(app, ["runs", "list", "--database", db])
        assert result.exit_code == 0


class TestHealthCommands:
    def test_check(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner.invoke(app, ["db", "init", "--database", db])
        result = runner.invoke(app, ["health", "check", "--database", db])
        assert result.exit_code == 0

    def test_capabilities(self, tmp_path):
        db = str(tmp_path / "test.db")
        runner.invoke(app, ["db", "init", "--database", db])
        result = runner.invoke(app, ["health", "capabilities", "--database", db])
        assert result.exit_code == 0
