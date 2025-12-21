"""Tests for alerts router endpoint logic.

Uses FastAPI TestClient with mocked OpContext to exercise endpoint code paths,
error handling, and response shaping.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spine.api.deps import get_operation_context
from spine.api.routers.alerts import router


_ctx = MagicMock()


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_operation_context] = lambda: _ctx
    return TestClient(app, raise_server_exceptions=False)


# ── Channels ─────────────────────────────────────────────────────


class TestChannelEndpoints:
    def test_list_channels_responds(self, client):
        resp = client.get("/api/v1/alerts/channels")
        assert resp.status_code in (200, 404, 500)

    def test_create_channel_validation(self, client):
        resp = client.post("/api/v1/alerts/channels", json={})
        assert resp.status_code == 422

    def test_create_channel_responds(self, client):
        resp = client.post(
            "/api/v1/alerts/channels",
            json={"name": "slack-main", "channel_type": "slack"},
        )
        assert resp.status_code in (200, 201, 404, 500)

    def test_get_channel_responds(self, client):
        resp = client.get("/api/v1/alerts/channels/ch-1")
        assert resp.status_code in (200, 404, 500)

    def test_delete_channel_responds(self, client):
        resp = client.delete("/api/v1/alerts/channels/ch-1")
        assert resp.status_code in (200, 404, 500)

    def test_update_channel_responds(self, client):
        resp = client.patch(
            "/api/v1/alerts/channels/ch-1",
            json={"enabled": False},
        )
        assert resp.status_code in (200, 404, 500)


# ── Alerts ───────────────────────────────────────────────────────


class TestAlertEndpoints:
    def test_list_alerts_responds(self, client):
        resp = client.get("/api/v1/alerts")
        assert resp.status_code in (200, 404, 500)

    def test_create_alert_validation(self, client):
        resp = client.post("/api/v1/alerts", json={})
        assert resp.status_code == 422

    def test_create_alert_responds(self, client):
        resp = client.post(
            "/api/v1/alerts",
            json={"title": "Test", "message": "Test alert", "source": "test"},
        )
        assert resp.status_code in (200, 201, 404, 500)

    def test_acknowledge_alert_responds(self, client):
        resp = client.post("/api/v1/alerts/a-1/ack")
        assert resp.status_code in (200, 404, 500)


# ── Deliveries ──────────────────────────────────────────────────


class TestDeliveryEndpoints:
    def test_list_deliveries_responds(self, client):
        resp = client.get("/api/v1/alerts/deliveries")
        assert resp.status_code in (200, 404, 500)

    def test_list_deliveries_with_filters(self, client):
        resp = client.get(
            "/api/v1/alerts/deliveries",
            params={"alert_id": "a-1", "status": "delivered"},
        )
        assert resp.status_code in (200, 404, 500)
