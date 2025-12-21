"""Tests for spine.api.routers.alerts — Pydantic schema unit tests.

Tests the Pydantic request/response schemas used by the alerts router,
and basic routing existence. Avoids deep integration (ops layer) since
response_model validation requires exact match on output shapes.
"""

from __future__ import annotations

import pytest

from spine.api.routers.alerts import (
    AlertChannelCreateRequest,
    AlertChannelDetailSchema,
    AlertChannelSchema,
    AlertChannelUpdateRequest,
    AlertCreateRequest,
    AlertDeliverySchema,
    AlertSchema,
)


class TestAlertChannelSchema:
    def test_defaults(self):
        s = AlertChannelSchema(id="ch-1", name="slack", channel_type="slack")
        assert s.min_severity == "ERROR"
        assert s.enabled is True
        assert s.consecutive_failures == 0

    def test_all_fields(self):
        s = AlertChannelSchema(
            id="ch-1", name="slack", channel_type="slack",
            min_severity="WARNING", enabled=False,
            consecutive_failures=3, created_at="2024-01-01",
        )
        assert s.min_severity == "WARNING"
        assert s.consecutive_failures == 3


class TestAlertChannelDetailSchema:
    def test_defaults(self):
        d = AlertChannelDetailSchema(id="ch-1", name="slack", channel_type="slack")
        assert d.config == {}
        assert d.throttle_minutes == 5
        assert d.domains is None

    def test_full(self):
        d = AlertChannelDetailSchema(
            id="ch-1", name="slack", channel_type="slack",
            config={"webhook_url": "https://hooks.slack.com/x"},
            min_severity="INFO", domains=["finance", "sec"],
            enabled=True, throttle_minutes=10,
            last_success_at="2024-01-01", last_failure_at=None,
            consecutive_failures=0, created_at="2024-01-01",
            updated_at="2024-01-02",
        )
        assert d.domains == ["finance", "sec"]
        assert d.throttle_minutes == 10


class TestAlertChannelCreateRequest:
    def test_required_fields(self):
        r = AlertChannelCreateRequest(name="slack-main", channel_type="slack")
        assert r.min_severity == "ERROR"
        assert r.enabled is True
        assert r.throttle_minutes == 5

    def test_with_config(self):
        r = AlertChannelCreateRequest(
            name="email-ops", channel_type="email",
            config={"to": "ops@example.com"},
            min_severity="CRITICAL", domains=["sec"],
        )
        assert r.config["to"] == "ops@example.com"
        assert r.domains == ["sec"]


class TestAlertChannelUpdateRequest:
    def test_all_none(self):
        r = AlertChannelUpdateRequest()
        assert r.enabled is None
        assert r.min_severity is None
        assert r.throttle_minutes is None

    def test_partial(self):
        r = AlertChannelUpdateRequest(enabled=False, throttle_minutes=15)
        assert r.enabled is False
        assert r.throttle_minutes == 15


class TestAlertSchema:
    def test_required(self):
        a = AlertSchema(
            id="a-1", severity="ERROR", title="Operation failed",
            message="ETL step 2 errored", source="worker-1",
        )
        assert a.domain is None

    def test_full(self):
        a = AlertSchema(
            id="a-1", severity="ERROR", title="Operation failed",
            message="ETL step 2 errored", source="worker-1",
            domain="finance", created_at="2024-01-01",
        )
        assert a.domain == "finance"


class TestAlertCreateRequest:
    def test_required(self):
        r = AlertCreateRequest(
            title="Alert", message="Something went wrong", source="test",
        )
        assert r.severity == "ERROR"  # default
        assert r.domain is None
        assert r.execution_id is None

    def test_full(self):
        r = AlertCreateRequest(
            severity="CRITICAL", title="Alert",
            message="Something went wrong", source="test",
            domain="finance", execution_id="exec-1",
            run_id="run-1", metadata={"key": "val"},
            error_category="TIMEOUT",
        )
        assert r.error_category == "TIMEOUT"
        assert r.metadata == {"key": "val"}


class TestAlertDeliverySchema:
    def test_required(self):
        d = AlertDeliverySchema(
            id="d-1", alert_id="a-1", channel_id="ch-1",
            channel_name="slack-main", status="delivered",
        )
        assert d.attempt == 1
        assert d.error is None

    def test_full(self):
        d = AlertDeliverySchema(
            id="d-1", alert_id="a-1", channel_id="ch-1",
            channel_name="slack-main", status="failed",
            attempted_at="2024-01-01",
            error="timeout", attempt=3,
        )
        assert d.attempt == 3
        assert d.error == "timeout"
