"""Tests for ``spine.ops.alerts`` — alert CRUD and delivery operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.ops.context import OperationContext
from spine.ops.alerts import (
    acknowledge_alert,
    create_alert,
    create_alert_channel,
    delete_alert_channel,
    get_alert_channel,
    list_alert_channels,
    list_alert_deliveries,
    list_alerts,
    update_alert_channel,
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


def _alert_row(**overrides):
    base = {
        "id": "alrt_001",
        "severity": "warning",
        "source": "monitor",
        "title": "High latency",
        "message": "Latency > 5s",
        "status": "active",
        "acknowledged": 0,
        "acknowledged_by": None,
        "acknowledged_at": None,
        "resolved": 0,
        "resolved_at": None,
        "operation_id": None,
        "workflow_id": None,
        "source_id": None,
        "metadata": None,
        "tags": None,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


def _channel_row(**overrides):
    base = {
        "id": "ch_001",
        "name": "email-ops",
        "channel_type": "email",
        "config": '{"to": "ops@example.com"}',
        "enabled": 1,
        "min_severity": "warning",
        "throttle_minutes": 15,
        "description": None,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# list_alerts
# ---------------------------------------------------------------------------

class TestListAlerts:
    @patch("spine.ops.alerts._alert_repo")
    def test_list_returns_paged(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_alerts.return_value = ([_alert_row()], 1)
        mock_repo_factory.return_value = repo

        from spine.ops.alerts import ListAlertsRequest
        result = list_alerts(ctx, ListAlertsRequest())
        assert result.success is True
        assert result.total == 1

    @patch("spine.ops.alerts._alert_repo")
    def test_list_empty(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_alerts.return_value = ([], 0)
        mock_repo_factory.return_value = repo

        from spine.ops.alerts import ListAlertsRequest
        result = list_alerts(ctx, ListAlertsRequest())
        assert result.total == 0

    @patch("spine.ops.alerts._alert_repo")
    def test_list_handles_exception(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_alerts.side_effect = Exception("DB error")
        mock_repo_factory.return_value = repo

        from spine.ops.alerts import ListAlertsRequest
        result = list_alerts(ctx, ListAlertsRequest())
        assert result.success is False


# ---------------------------------------------------------------------------
# create_alert
# ---------------------------------------------------------------------------

class TestCreateAlert:
    @patch("spine.ops.alerts._alert_repo")
    def test_create_success(self, mock_repo_factory, ctx):
        repo = MagicMock()
        mock_repo_factory.return_value = repo

        from spine.ops.alerts import CreateAlertRequest
        result = create_alert(ctx, CreateAlertRequest(
            severity="warning",
            source="test",
            title="Test alert",
            message="Something happened",
        ))
        assert result.success is True
        repo.create_alert.assert_called_once()


# ---------------------------------------------------------------------------
# acknowledge_alert
# ---------------------------------------------------------------------------

class TestAcknowledgeAlert:
    @patch("spine.ops.alerts._alert_repo")
    def test_acknowledge_success(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.get_alert.return_value = _alert_row()
        mock_repo_factory.return_value = repo

        result = acknowledge_alert(ctx, "alrt_001", acknowledged_by="admin")
        assert result.success is True
        repo.update_alert_metadata.assert_called_once()

    @patch("spine.ops.alerts._alert_repo")
    def test_acknowledge_not_found(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.get_alert.return_value = None
        mock_repo_factory.return_value = repo

        result = acknowledge_alert(ctx, "alrt_missing")
        assert result.success is False


# ---------------------------------------------------------------------------
# Alert channels
# ---------------------------------------------------------------------------

class TestAlertChannels:
    @patch("spine.ops.alerts._alert_repo")
    def test_list_channels(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_channels.return_value = ([_channel_row()], 1)
        mock_repo_factory.return_value = repo

        from spine.ops.alerts import ListAlertChannelsRequest
        result = list_alert_channels(ctx, ListAlertChannelsRequest())
        assert result.success is True

    @patch("spine.ops.alerts._alert_repo")
    def test_get_channel(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.get_channel.return_value = _channel_row()
        mock_repo_factory.return_value = repo

        result = get_alert_channel(ctx, "ch_001")
        assert result.success is True

    @patch("spine.ops.alerts._alert_repo")
    def test_get_channel_not_found(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.get_channel.return_value = None
        mock_repo_factory.return_value = repo

        result = get_alert_channel(ctx, "ch_missing")
        assert result.success is False

    @patch("spine.ops.alerts._alert_repo")
    def test_create_channel(self, mock_repo_factory, ctx):
        repo = MagicMock()
        mock_repo_factory.return_value = repo

        from spine.ops.alerts import CreateAlertChannelRequest
        result = create_alert_channel(ctx, CreateAlertChannelRequest(
            name="slack-alerts",
            channel_type="slack",
            config={"webhook_url": "https://hooks.slack.com/xxx"},
        ))
        assert result.success is True

    @patch("spine.ops.alerts._alert_repo")
    def test_delete_channel_dry_run(self, mock_repo_factory, dry_ctx):
        result = delete_alert_channel(dry_ctx, "ch_001")
        assert result.success is True
        assert result.data.get("dry_run") is True

    @patch("spine.ops.alerts._alert_repo")
    def test_delete_channel_success(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.delete_channel.return_value = True
        mock_repo_factory.return_value = repo
        result = delete_alert_channel(ctx, "ch_001")
        assert result.success is True

    @patch("spine.ops.alerts._alert_repo")
    def test_update_channel(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.update_channel.return_value = True
        mock_repo_factory.return_value = repo
        result = update_alert_channel(ctx, "ch_001", enabled=False)
        assert result.success is True


# ---------------------------------------------------------------------------
# Alert deliveries
# ---------------------------------------------------------------------------

class TestAlertDeliveries:
    @patch("spine.ops.alerts._alert_repo")
    def test_list_deliveries(self, mock_repo_factory, ctx):
        repo = MagicMock()
        repo.list_deliveries.return_value = ([], 0)
        mock_repo_factory.return_value = repo

        from spine.ops.alerts import ListAlertDeliveriesRequest
        result = list_alert_deliveries(ctx, ListAlertDeliveriesRequest())
        assert result.success is True
