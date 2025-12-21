"""Tests for spine.cli — CLI command smoke tests via CliRunner.

Tests cover config, alerts, sources, and profile sub-commands using
typer.testing.CliRunner with mocked OperationContext so no real DB is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from spine.cli.app import app

runner = CliRunner()


# ─── Config commands ─────────────────────────────────────────────────────


class TestConfigCLI:
    """Tests for the 'config' sub-commands."""

    @patch("spine.core.config.get_settings")
    def test_config_show_json(self, mock_settings):
        """config show --format json should output JSON."""
        mock_obj = MagicMock()
        mock_obj.model_dump_json.return_value = '{"database_backend": "sqlite"}'
        mock_settings.return_value = mock_obj
        result = runner.invoke(app, ["config", "show", "--format", "json"])
        assert result.exit_code == 0

    @patch("spine.core.config.get_settings")
    def test_config_show_env(self, mock_settings):
        """config show --format env should output KEY=VALUE."""
        mock_obj = MagicMock()
        mock_obj.model_dump.return_value = {"database_backend": "sqlite", "cache_backend": "memory"}
        mock_settings.return_value = mock_obj
        result = runner.invoke(app, ["config", "show", "--format", "env"])
        assert result.exit_code == 0

    @patch("spine.core.config.get_settings")
    def test_config_show_table(self, mock_settings):
        """config show (default table format)."""
        mock_obj = MagicMock()
        mock_obj.infer_tier.return_value = "minimal"
        mock_obj.database_backend = MagicMock(value="sqlite")
        mock_obj.scheduler_backend = MagicMock(value="apscheduler")
        mock_obj.cache_backend = MagicMock(value="memory")
        mock_obj.worker_backend = MagicMock(value="local")
        mock_obj.metrics_backend = MagicMock(value="none")
        mock_obj.tracing_backend = MagicMock(value="none")
        mock_obj.model_dump.return_value = {}
        mock_settings.return_value = mock_obj
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0

    @patch("spine.core.config.get_settings")
    def test_config_validate_ok(self, mock_settings):
        """config validate should show tier and warnings."""
        mock_obj = MagicMock()
        mock_obj.infer_tier.return_value = "standard"
        mock_obj.component_warnings = []
        mock_settings.return_value = mock_obj
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        assert "No compatibility warnings" in result.output or "standard" in result.output

    @patch("spine.core.config.get_settings")
    def test_config_validate_error(self, mock_settings):
        """config validate should report config errors."""
        mock_settings.side_effect = ValueError("bad config")
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 1

    @patch("spine.core.config.find_project_root")
    def test_config_init_no_source(self, mock_root, tmp_path):
        """config init should fail if source env file doesn't exist."""
        mock_root.return_value = tmp_path
        result = runner.invoke(app, ["config", "init", "--tier", "minimal"])
        assert result.exit_code == 1

    @patch("spine.core.config.find_project_root")
    def test_config_init_exists(self, mock_root, tmp_path):
        """config init should warn if target already exists."""
        mock_root.return_value = tmp_path
        (tmp_path / ".env.minimal").write_text("X=1")
        (tmp_path / ".env.local").write_text("existing")
        result = runner.invoke(app, ["config", "init", "--tier", "minimal"])
        assert result.exit_code == 1

    @patch("spine.core.config.find_project_root")
    def test_config_init_force(self, mock_root, tmp_path):
        """config init --force should overwrite existing file."""
        mock_root.return_value = tmp_path
        (tmp_path / ".env.minimal").write_text("X=1")
        (tmp_path / ".env.local").write_text("existing")
        result = runner.invoke(app, ["config", "init", "--tier", "minimal", "--force"])
        assert result.exit_code == 0
        assert (tmp_path / ".env.local").read_text() == "X=1"

    @patch("spine.core.config.get_settings")
    def test_config_tier(self, mock_settings):
        """config tier should output tier name."""
        mock_obj = MagicMock()
        mock_obj.infer_tier.return_value = "full"
        mock_settings.return_value = mock_obj
        result = runner.invoke(app, ["config", "tier"])
        assert result.exit_code == 0

    @patch("spine.core.config.discover_env_files")
    @patch("spine.core.config.find_project_root")
    def test_config_env(self, mock_root, mock_discover, tmp_path):
        """config env should list env files."""
        mock_root.return_value = tmp_path
        mock_discover.return_value = [tmp_path / ".env"]
        result = runner.invoke(app, ["config", "env"])
        assert result.exit_code == 0


# ─── Alert commands ──────────────────────────────────────────────────────


class TestAlertsCLI:
    """Tests for the 'alerts' sub-commands."""

    def _mock_paged(self, items=None, total=0):
        from spine.ops.result import PagedResult
        pr = MagicMock(spec=PagedResult)
        pr.success = True
        pr.error = None
        pr.items = items or []
        pr.total = total
        return pr

    def _mock_result(self, success=True, data=None, error=None):
        from spine.ops.result import OperationResult
        r = MagicMock(spec=OperationResult)
        r.success = success
        r.data = data or {}
        r.error = error
        return r

    @patch("spine.ops.alerts.list_alerts")
    @patch("spine.cli.utils.make_context")
    def test_alerts_list_json(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = self._mock_paged()
        result = runner.invoke(app, ["alerts", "list", "--json"])
        assert result.exit_code == 0

    @patch("spine.ops.alerts.list_alert_channels")
    @patch("spine.cli.utils.make_context")
    def test_alerts_channels(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = self._mock_paged()
        result = runner.invoke(app, ["alerts", "channels", "--json"])
        assert result.exit_code == 0

    @patch("spine.ops.alerts.get_alert_channel")
    @patch("spine.cli.utils.make_context")
    def test_alerts_channel_get(self, mock_ctx, mock_get):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_get.return_value = self._mock_result(data={"id": "ch-1", "name": "slack"})
        result = runner.invoke(app, ["alerts", "channel-get", "ch-1", "--json"])
        assert result.exit_code == 0

    @patch("spine.ops.alerts.delete_alert_channel")
    @patch("spine.cli.utils.make_context")
    def test_alerts_channel_delete_force(self, mock_ctx, mock_delete):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_delete.return_value = self._mock_result()
        result = runner.invoke(app, ["alerts", "channel-delete", "ch-1", "--force"])
        assert result.exit_code == 0

    @patch("spine.ops.alerts.create_alert_channel")
    @patch("spine.cli.utils.make_context")
    def test_alerts_channel_create(self, mock_ctx, mock_create):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_create.return_value = self._mock_result(data={"id": "ch-new"})
        result = runner.invoke(app, ["alerts", "channel-create", "test-chan", "--type", "slack", "--json"])
        assert result.exit_code == 0

    @patch("spine.ops.alerts.update_alert_channel")
    @patch("spine.cli.utils.make_context")
    def test_alerts_channel_enable(self, mock_ctx, mock_update):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_update.return_value = self._mock_result()
        result = runner.invoke(app, ["alerts", "channel-enable", "ch-1"])
        assert result.exit_code == 0

    @patch("spine.ops.alerts.update_alert_channel")
    @patch("spine.cli.utils.make_context")
    def test_alerts_channel_disable(self, mock_ctx, mock_update):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_update.return_value = self._mock_result()
        result = runner.invoke(app, ["alerts", "channel-disable", "ch-1"])
        assert result.exit_code == 0

    @patch("spine.ops.alerts.acknowledge_alert")
    @patch("spine.cli.utils.make_context")
    def test_alerts_ack(self, mock_ctx, mock_ack):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_ack.return_value = self._mock_result()
        result = runner.invoke(app, ["alerts", "ack", "alert-1"])
        assert result.exit_code == 0

    @patch("spine.ops.alerts.list_alert_deliveries")
    @patch("spine.cli.utils.make_context")
    def test_alerts_deliveries(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = self._mock_paged()
        result = runner.invoke(app, ["alerts", "deliveries", "--json"])
        assert result.exit_code == 0


# ─── Sources commands ─────────────────────────────────────────────────────


class TestSourcesCLI:
    """Tests for the 'sources' sub-commands."""

    def _mock_paged(self, items=None, total=0):
        from spine.ops.result import PagedResult
        pr = MagicMock(spec=PagedResult)
        pr.success = True
        pr.error = None
        pr.items = items or []
        pr.total = total
        return pr

    def _mock_result(self, success=True, data=None, error=None):
        from spine.ops.result import OperationResult
        r = MagicMock(spec=OperationResult)
        r.success = success
        r.data = data or {}
        r.error = error
        return r

    @patch("spine.ops.sources.list_sources")
    @patch("spine.cli.utils.make_context")
    def test_sources_list(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = self._mock_paged()
        result = runner.invoke(app, ["sources", "list", "--json"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.register_source")
    @patch("spine.cli.utils.make_context")
    def test_sources_register(self, mock_ctx, mock_reg):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_reg.return_value = self._mock_result(data={"id": "src-1", "name": "test"})
        result = runner.invoke(app, ["sources", "register", "my-src", "--type", "file", "--json"])
        assert result.exit_code == 0

    def test_sources_register_bad_json(self):
        result = runner.invoke(app, ["sources", "register", "my-src", "--config", "{bad"])
        assert result.exit_code == 1

    @patch("spine.ops.sources.get_source")
    @patch("spine.cli.utils.make_context")
    def test_sources_get(self, mock_ctx, mock_get):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_get.return_value = self._mock_result(data={"id": "src-1"})
        result = runner.invoke(app, ["sources", "get", "src-1", "--json"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.delete_source")
    @patch("spine.cli.utils.make_context")
    def test_sources_delete_force(self, mock_ctx, mock_delete):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_delete.return_value = self._mock_result()
        result = runner.invoke(app, ["sources", "delete", "src-1", "--force"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.enable_source")
    @patch("spine.cli.utils.make_context")
    def test_sources_enable(self, mock_ctx, mock_enable):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_enable.return_value = self._mock_result()
        result = runner.invoke(app, ["sources", "enable", "src-1"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.disable_source")
    @patch("spine.cli.utils.make_context")
    def test_sources_disable(self, mock_ctx, mock_disable):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_disable.return_value = self._mock_result()
        result = runner.invoke(app, ["sources", "disable", "src-1"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.list_source_fetches")
    @patch("spine.cli.utils.make_context")
    def test_sources_fetches(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = self._mock_paged()
        result = runner.invoke(app, ["sources", "fetches", "--json"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.list_source_cache")
    @patch("spine.cli.utils.make_context")
    def test_sources_cache(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = self._mock_paged()
        result = runner.invoke(app, ["sources", "cache", "--json"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.invalidate_source_cache")
    @patch("spine.cli.utils.make_context")
    def test_sources_cache_invalidate(self, mock_ctx, mock_inv):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_inv.return_value = self._mock_result(data={"deleted": 5})
        result = runner.invoke(app, ["sources", "cache-invalidate", "src-1", "--force"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.list_database_connections")
    @patch("spine.cli.utils.make_context")
    def test_sources_connections(self, mock_ctx, mock_list):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_list.return_value = self._mock_paged()
        result = runner.invoke(app, ["sources", "connections", "--json"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.register_database_connection")
    @patch("spine.cli.utils.make_context")
    def test_sources_connection_register(self, mock_ctx, mock_reg):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_reg.return_value = self._mock_result(data={"id": "conn-1"})
        result = runner.invoke(app, [
            "sources", "connection-register", "myconn",
            "--dialect", "postgresql", "--db", "testdb", "--json",
        ])
        assert result.exit_code == 0

    @patch("spine.ops.sources.delete_database_connection")
    @patch("spine.cli.utils.make_context")
    def test_sources_connection_delete_force(self, mock_ctx, mock_delete):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_delete.return_value = self._mock_result()
        result = runner.invoke(app, ["sources", "connection-delete", "conn-1", "--force"])
        assert result.exit_code == 0

    @patch("spine.ops.sources.test_database_connection")
    @patch("spine.cli.utils.make_context")
    def test_sources_connection_test(self, mock_ctx, mock_test):
        mock_ctx.return_value = (MagicMock(), MagicMock())
        mock_test.return_value = self._mock_result(data={"connected": True})
        result = runner.invoke(app, ["sources", "connection-test", "conn-1", "--json"])
        assert result.exit_code == 0


# ─── Profile commands ────────────────────────────────────────────────────


class TestProfileCLI:
    """Tests for the 'profile' sub-commands."""

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_list_empty(self, mock_mgr):
        mgr = MagicMock()
        mgr.list_profiles.return_value = []
        mgr.get_active_profile.return_value = None
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "list"])
        assert result.exit_code == 0
        assert "No profiles" in result.output

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_list_with_profiles(self, mock_mgr):
        mgr = MagicMock()
        p = MagicMock()
        p.name = "dev"
        p.path = "/project/.spine/dev.toml"
        p.inherits = None
        p.description = "Dev profile"
        mgr.list_profiles.return_value = [p]
        mgr.get_active_profile.return_value = "dev"
        mgr.project_profile_dir = "/project/.spine"
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "list"])
        assert result.exit_code == 0

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_show_not_found(self, mock_mgr):
        mgr = MagicMock()
        mgr.get_profile.return_value = None
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "show", "nonexistent"])
        assert result.exit_code == 1

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_show_json(self, mock_mgr):
        mgr = MagicMock()
        p = MagicMock()
        p.name = "dev"
        p.path = "/dev.toml"
        p.inherits = None
        p.description = "Dev"
        p.settings = {"key": "val"}
        mgr.get_profile.return_value = p
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "show", "dev", "--format", "json"])
        assert result.exit_code == 0

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_show_env(self, mock_mgr):
        mgr = MagicMock()
        p = MagicMock()
        p.name = "dev"
        p.path = "/dev.toml"
        p.inherits = None
        p.description = "Dev"
        p.settings = {"key": "val"}
        mgr.get_profile.return_value = p
        mgr.resolve_profile.return_value = {"KEY": "val"}
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "show", "dev", "--format", "env"])
        assert result.exit_code == 0
        assert "KEY=val" in result.output

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_show_table(self, mock_mgr):
        mgr = MagicMock()
        p = MagicMock()
        p.name = "dev"
        p.path = "/dev.toml"
        p.inherits = "base"
        p.description = "Dev"
        p.settings = {"key": "val", "section": {"sub": "value"}}
        mgr.get_profile.return_value = p
        mgr.resolve_profile.return_value = {"key": "val", "sub": "value"}
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "show", "dev"])
        assert result.exit_code == 0

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_create(self, mock_mgr):
        mgr = MagicMock()
        mgr.get_profile.return_value = None
        new_p = MagicMock()
        new_p.path = "/profiles/test.toml"
        mgr.create_profile.return_value = new_p
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "create", "test"])
        assert result.exit_code == 0

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_create_already_exists(self, mock_mgr):
        mgr = MagicMock()
        mgr.get_profile.return_value = MagicMock()
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "create", "existing"])
        assert result.exit_code == 1

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_use(self, mock_mgr):
        mgr = MagicMock()
        mgr.get_profile.return_value = MagicMock()
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "use", "dev"])
        assert result.exit_code == 0

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_use_not_found(self, mock_mgr):
        mgr = MagicMock()
        mgr.get_profile.return_value = None
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "use", "missing"])
        assert result.exit_code == 1

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_delete(self, mock_mgr):
        mgr = MagicMock()
        mgr.get_profile.return_value = MagicMock()
        mgr.delete_profile.return_value = True
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "delete", "dev", "--force"])
        assert result.exit_code == 0

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_delete_not_found(self, mock_mgr):
        mgr = MagicMock()
        mgr.get_profile.return_value = None
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "delete", "missing", "--force"])
        assert result.exit_code == 1

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_active(self, mock_mgr):
        mgr = MagicMock()
        mgr.get_active_profile.return_value = "dev"
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "active"])
        assert result.exit_code == 0

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_active_none(self, mock_mgr):
        mgr = MagicMock()
        mgr.get_active_profile.return_value = None
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "active"])
        assert result.exit_code == 0

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_export(self, mock_mgr):
        mgr = MagicMock()
        mgr.get_profile.return_value = MagicMock()
        mgr.resolve_profile.return_value = {"A": "1", "B": "2"}
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "export", "dev"])
        assert result.exit_code == 0

    @patch("spine.core.config.profiles.get_profile_manager")
    def test_profile_export_not_found(self, mock_mgr):
        mgr = MagicMock()
        mgr.get_profile.return_value = None
        mock_mgr.return_value = mgr
        result = runner.invoke(app, ["profile", "export", "missing"])
        assert result.exit_code == 1


# ─── Deploy commands (just --help since they need Docker) ────────────────


class TestDeployCLI:
    """Smoke test that deploy commands are registered."""

    def test_deploy_help(self):
        result = runner.invoke(app, ["deploy", "--help"])
        assert result.exit_code == 0
        assert "testbed" in result.output

    def test_deploy_testbed_help(self):
        result = runner.invoke(app, ["deploy", "testbed", "--help"])
        assert result.exit_code == 0
        assert "backend" in result.output


# ─── Root --version ──────────────────────────────────────────────────────


class TestRootCLI:
    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "spine-core" in result.output

    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "workflow" in result.output
