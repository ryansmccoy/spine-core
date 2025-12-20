"""Tests for spine.ops.alerts — alert channel, alert, and delivery operations."""

import json

from spine.ops.database import initialize_database
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
from spine.ops.requests import (
    CreateAlertChannelRequest,
    CreateAlertRequest,
    ListAlertChannelsRequest,
    ListAlertDeliveriesRequest,
    ListAlertsRequest,
)


# ------------------------------------------------------------------ #
# Alert Channels
# ------------------------------------------------------------------ #


def _insert_channel(ctx, channel_id="ch_test1", name="slack-prod",
                     channel_type="slack", enabled=1, min_severity="ERROR"):
    """Insert a test alert channel row."""
    ctx.conn.execute(
        """
        INSERT INTO core_alert_channels (
            id, name, channel_type, config_json, min_severity,
            domains, enabled, throttle_minutes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (channel_id, name, channel_type, '{"webhook_url": "https://example.com"}',
         min_severity, None, enabled, 5),
    )
    ctx.conn.commit()


class TestListAlertChannels:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_alert_channels(ctx, ListAlertChannelsRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_channel(ctx)
        result = list_alert_channels(ctx, ListAlertChannelsRequest())
        assert result.success is True
        assert result.total == 1
        assert len(result.data) == 1
        assert result.data[0].name == "slack-prod"
        assert result.data[0].channel_type == "slack"

    def test_filter_by_type(self, ctx):
        initialize_database(ctx)
        _insert_channel(ctx, "ch_1", "slack-prod", "slack")
        _insert_channel(ctx, "ch_2", "email-ops", "email")

        result = list_alert_channels(ctx, ListAlertChannelsRequest(channel_type="email"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].name == "email-ops"

    def test_filter_by_enabled(self, ctx):
        initialize_database(ctx)
        _insert_channel(ctx, "ch_1", "active", "slack", enabled=1)
        _insert_channel(ctx, "ch_2", "disabled", "slack", enabled=0)

        result = list_alert_channels(ctx, ListAlertChannelsRequest(enabled=True))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].name == "active"

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            _insert_channel(ctx, f"ch_{i}", f"channel-{i}", "slack")

        result = list_alert_channels(ctx, ListAlertChannelsRequest(limit=2, offset=0))
        assert result.success is True
        assert result.total == 5
        assert len(result.data) == 2
        assert result.has_more is True


class TestGetAlertChannel:
    def test_not_found(self, ctx):
        initialize_database(ctx)
        result = get_alert_channel(ctx, "nonexistent")
        assert result.success is False
        assert result.error.code == "NOT_FOUND"

    def test_found(self, ctx):
        initialize_database(ctx)
        _insert_channel(ctx)
        result = get_alert_channel(ctx, "ch_test1")
        assert result.success is True
        assert result.data.name == "slack-prod"
        assert result.data.channel_type == "slack"
        assert result.data.min_severity == "ERROR"
        assert result.data.enabled is True


class TestCreateAlertChannel:
    def test_create(self, ctx):
        initialize_database(ctx)
        request = CreateAlertChannelRequest(
            name="new-channel",
            channel_type="webhook",
            config={"url": "https://hooks.example.com"},
            min_severity="WARNING",
        )
        result = create_alert_channel(ctx, request)
        assert result.success is True
        assert result.data["created"] is True
        assert result.data["name"] == "new-channel"
        assert "id" in result.data

    def test_create_dry_run(self, dry_ctx):
        initialize_database(dry_ctx)
        request = CreateAlertChannelRequest(name="dry-test")
        result = create_alert_channel(dry_ctx, request)
        assert result.success is True
        assert result.data["dry_run"] is True
        assert result.data["would_create"] == "dry-test"


class TestDeleteAlertChannel:
    def test_delete(self, ctx):
        initialize_database(ctx)
        _insert_channel(ctx)
        result = delete_alert_channel(ctx, "ch_test1")
        assert result.success is True
        assert result.data["deleted"] is True

        # Verify gone
        check = get_alert_channel(ctx, "ch_test1")
        assert check.success is False

    def test_delete_dry_run(self, ctx):
        initialize_database(ctx)
        _insert_channel(ctx)
        result = delete_alert_channel(ctx, "ch_test1", dry_run=True)
        assert result.success is True
        assert result.data["dry_run"] is True

        # Verify still exists
        check = get_alert_channel(ctx, "ch_test1")
        assert check.success is True


class TestUpdateAlertChannel:
    def test_update_enabled(self, ctx):
        initialize_database(ctx)
        _insert_channel(ctx)
        result = update_alert_channel(ctx, "ch_test1", enabled=False)
        assert result.success is True
        assert result.data["updated"] is True

    def test_update_severity(self, ctx):
        initialize_database(ctx)
        _insert_channel(ctx)
        result = update_alert_channel(ctx, "ch_test1", min_severity="CRITICAL")
        assert result.success is True

    def test_update_throttle(self, ctx):
        initialize_database(ctx)
        _insert_channel(ctx)
        result = update_alert_channel(ctx, "ch_test1", throttle_minutes=30)
        assert result.success is True

    def test_update_no_fields(self, ctx):
        initialize_database(ctx)
        _insert_channel(ctx)
        result = update_alert_channel(ctx, "ch_test1")
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_update_dry_run(self, dry_ctx):
        initialize_database(dry_ctx)
        result = update_alert_channel(dry_ctx, "ch_test1", enabled=True)
        assert result.success is True
        assert result.data["dry_run"] is True


# ------------------------------------------------------------------ #
# Alerts
# ------------------------------------------------------------------ #


def _insert_alert(ctx, alert_id="alert_test1", severity="ERROR",
                   title="Test Alert", source="test-pipeline"):
    """Insert a test alert row."""
    ctx.conn.execute(
        """
        INSERT INTO core_alerts (
            id, severity, title, message, source, domain,
            created_at, dedup_key
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?)
        """,
        (alert_id, severity, title, "Alert description", source, "test",
         f"dedup_{alert_id}"),
    )
    ctx.conn.commit()


class TestListAlerts:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_alerts(ctx, ListAlertsRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_alert(ctx)
        result = list_alerts(ctx, ListAlertsRequest())
        assert result.success is True
        assert result.total == 1
        assert result.data[0].title == "Test Alert"

    def test_filter_by_severity(self, ctx):
        initialize_database(ctx)
        _insert_alert(ctx, "a1", "ERROR", "Error Alert")
        _insert_alert(ctx, "a2", "WARNING", "Warning Alert")

        result = list_alerts(ctx, ListAlertsRequest(severity="WARNING"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].severity == "WARNING"

    def test_filter_by_source(self, ctx):
        initialize_database(ctx)
        _insert_alert(ctx, "a1", source="pipeline-a")
        _insert_alert(ctx, "a2", source="pipeline-b")

        result = list_alerts(ctx, ListAlertsRequest(source="pipeline-a"))
        assert result.success is True
        assert result.total == 1
        assert result.data[0].source == "pipeline-a"

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            _insert_alert(ctx, f"a_{i}")

        result = list_alerts(ctx, ListAlertsRequest(limit=2, offset=0))
        assert result.success is True
        assert result.total == 5
        assert len(result.data) == 2
        assert result.has_more is True


class TestCreateAlert:
    def test_create(self, ctx):
        initialize_database(ctx)
        request = CreateAlertRequest(
            severity="CRITICAL",
            title="Disk Full",
            message="Root partition is 99% full",
            source="monitoring",
        )
        result = create_alert(ctx, request)
        assert result.success is True
        assert result.data["created"] is True
        assert "id" in result.data
        assert "dedup_key" in result.data

    def test_create_dry_run(self, dry_ctx):
        initialize_database(dry_ctx)
        request = CreateAlertRequest(title="Dry Alert")
        result = create_alert(dry_ctx, request)
        assert result.success is True
        assert result.data["dry_run"] is True


class TestAcknowledgeAlert:
    def test_acknowledge(self, ctx):
        initialize_database(ctx)
        _insert_alert(ctx)
        result = acknowledge_alert(ctx, "alert_test1", acknowledged_by="admin")
        assert result.success is True
        assert result.data["acknowledged"] is True

    def test_acknowledge_not_found(self, ctx):
        initialize_database(ctx)
        result = acknowledge_alert(ctx, "nonexistent")
        assert result.success is False
        assert result.error.code == "NOT_FOUND"

    def test_acknowledge_dry_run(self, dry_ctx):
        initialize_database(dry_ctx)
        result = acknowledge_alert(dry_ctx, "any-id")
        assert result.success is True
        assert result.data["dry_run"] is True


# ------------------------------------------------------------------ #
# Alert Deliveries
# ------------------------------------------------------------------ #


def _insert_delivery(ctx, delivery_id="del_test1", alert_id="alert_test1",
                      channel_id="ch_test1", status="SENT"):
    """Insert a test alert delivery row."""
    ctx.conn.execute(
        """
        INSERT INTO core_alert_deliveries (
            id, alert_id, channel_id, channel_name, status,
            attempted_at, delivered_at, attempt, created_at
        ) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), 1, datetime('now'))
        """,
        (delivery_id, alert_id, channel_id, "slack-prod", status),
    )
    ctx.conn.commit()


class TestListAlertDeliveries:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_alert_deliveries(ctx, ListAlertDeliveriesRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_delivery(ctx)
        result = list_alert_deliveries(ctx, ListAlertDeliveriesRequest())
        assert result.success is True
        assert result.total == 1
        assert result.data[0].status == "SENT"

    def test_filter_by_alert(self, ctx):
        initialize_database(ctx)
        _insert_delivery(ctx, "d1", "alert_1", "ch_1")
        _insert_delivery(ctx, "d2", "alert_2", "ch_1")

        result = list_alert_deliveries(
            ctx, ListAlertDeliveriesRequest(alert_id="alert_1")
        )
        assert result.success is True
        assert result.total == 1
        assert result.data[0].alert_id == "alert_1"

    def test_filter_by_channel(self, ctx):
        initialize_database(ctx)
        _insert_delivery(ctx, "d1", "a1", "ch_1")
        _insert_delivery(ctx, "d2", "a2", "ch_2")

        result = list_alert_deliveries(
            ctx, ListAlertDeliveriesRequest(channel_id="ch_1")
        )
        assert result.success is True
        assert result.total == 1

    def test_filter_by_status(self, ctx):
        initialize_database(ctx)
        _insert_delivery(ctx, "d1", status="SENT")
        _insert_delivery(ctx, "d2", "a2", "ch_2", status="FAILED")

        result = list_alert_deliveries(
            ctx, ListAlertDeliveriesRequest(status="FAILED")
        )
        assert result.success is True
        assert result.total == 1
        assert result.data[0].status == "FAILED"

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            _insert_delivery(ctx, f"d_{i}", f"a_{i}", f"ch_{i}")

        result = list_alert_deliveries(
            ctx, ListAlertDeliveriesRequest(limit=2, offset=0)
        )
        assert result.success is True
        assert result.total == 5
        assert len(result.data) == 2
        assert result.has_more is True
