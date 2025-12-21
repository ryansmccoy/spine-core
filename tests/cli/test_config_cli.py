"""Tests for spine.cli.config — config show/validate/init/tier/env commands.

Extends coverage for branch paths in show_config (env format, all_settings,
table format details) and validate_config (warnings path).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from spine.cli.config import app

runner = CliRunner()


class TestShowConfig:
    @patch("spine.core.config.get_settings")
    def test_show_json_format(self, mock_settings):
        settings = MagicMock()
        settings.model_dump_json.return_value = '{"database_backend":"sqlite"}'
        mock_settings.return_value = settings

        result = runner.invoke(app, ["show", "--format", "json"])
        assert result.exit_code == 0

    @patch("spine.core.config.get_settings")
    def test_show_env_format(self, mock_settings):
        settings = MagicMock()
        settings.model_dump.return_value = {
            "database_backend": "sqlite",
            "_private": "skip",
        }
        mock_settings.return_value = settings

        result = runner.invoke(app, ["show", "--format", "env"])
        assert result.exit_code == 0
        assert "SPINE_DATABASE_BACKEND=sqlite" in result.output

    @patch("spine.core.config.get_settings")
    def test_show_table_format(self, mock_settings):
        settings = MagicMock()
        settings.infer_tier.return_value = "minimal"
        settings.database_backend.value = "sqlite"
        settings.scheduler_backend.value = "thread"
        settings.cache_backend.value = "memory"
        settings.worker_backend.value = "thread"
        settings.metrics_backend.value = "null"
        settings.tracing_backend.value = "null"
        settings._project_root = None
        settings._env_files_loaded = []
        settings._active_profile = None
        settings.model_dump.return_value = {"database_backend": "sqlite"}
        mock_settings.return_value = settings

        result = runner.invoke(app, ["show"])
        assert result.exit_code == 0

    @patch("spine.core.config.get_settings")
    def test_show_all_settings(self, mock_settings):
        settings = MagicMock()
        settings.infer_tier.return_value = "minimal"
        settings.database_backend.value = "sqlite"
        settings.scheduler_backend.value = "thread"
        settings.cache_backend.value = "memory"
        settings.worker_backend.value = "thread"
        settings.metrics_backend.value = "null"
        settings.tracing_backend.value = "null"
        settings.model_dump.return_value = {
            "database_backend": "sqlite",
            "_private": "skip",
        }
        mock_settings.return_value = settings

        result = runner.invoke(app, ["show", "--all"])
        assert result.exit_code == 0
        assert "database_backend" in result.output


class TestValidateConfig:
    @patch("spine.core.config.get_settings")
    def test_validate_no_warnings(self, mock_settings):
        settings = MagicMock()
        settings.infer_tier.return_value = "minimal"
        settings.component_warnings = []
        mock_settings.return_value = settings

        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0

    @patch("spine.core.config.get_settings")
    def test_validate_with_warnings(self, mock_settings):
        warning = MagicMock()
        warning.severity = "warning"
        warning.message = "Redis not configured"
        warning.suggestion = "Set SPINE_CACHE_URL"

        settings = MagicMock()
        settings.infer_tier.return_value = "minimal"
        settings.component_warnings = [warning]
        mock_settings.return_value = settings

        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0
        assert "Redis not configured" in result.output

    @patch("spine.core.config.get_settings")
    def test_validate_error(self, mock_settings):
        mock_settings.side_effect = ValueError("bad config")

        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 1


class TestTierCommand:
    @patch("spine.core.config.get_settings")
    def test_show_tier(self, mock_settings):
        settings = MagicMock()
        settings.infer_tier.return_value = "full"
        mock_settings.return_value = settings

        result = runner.invoke(app, ["tier"])
        assert result.exit_code == 0
        assert "full" in result.output


class TestEnvCommand:
    @patch("spine.core.config.discover_env_files")
    @patch("spine.core.config.find_project_root")
    def test_show_env_files(self, mock_root, mock_discover):
        mock_root.return_value = "/tmp/project"
        mock_discover.return_value = ["/tmp/project/.env", "/tmp/project/.env.local"]

        result = runner.invoke(app, ["env"])
        assert result.exit_code == 0
