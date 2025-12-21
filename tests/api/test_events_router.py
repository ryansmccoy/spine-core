"""Tests for spine.api.routers.events — event bus endpoints.

Tests the event bus status, publish, and recent event endpoints
using a minimal FastAPI TestClient.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spine.api.routers.events import router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


class TestEventBusStatus:
    """GET /events/status tests."""

    @patch("spine.core.events.get_event_bus")
    def test_status_returns_backend(self, mock_bus):
        bus = MagicMock()
        bus.subscription_count = 3
        bus._closed = False
        mock_bus.return_value = bus
        client = TestClient(_make_app())
        resp = client.get("/api/v1/events/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "backend" in data
        assert data["subscription_count"] == 3
        assert data["closed"] is False

    @patch("spine.core.events.get_event_bus")
    def test_status_no_subscription_count(self, mock_bus):
        bus = MagicMock(spec=[])  # no attributes
        mock_bus.return_value = bus
        client = TestClient(_make_app())
        resp = client.get("/api/v1/events/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription_count"] == 0


class TestPublishEvent:
    """POST /events/publish tests."""

    @patch("spine.core.events.get_event_bus")
    def test_publish_event_success(self, mock_bus):
        bus = MagicMock()
        bus.publish = AsyncMock()
        mock_bus.return_value = bus
        client = TestClient(_make_app())
        resp = client.post(
            "/api/v1/events/publish",
            json={"event_type": "test.event", "source": "api", "payload": {"x": 1}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["event_type"] == "test.event"
        bus.publish.assert_called_once()

    @patch("spine.core.events.get_event_bus")
    def test_publish_with_correlation_id(self, mock_bus):
        bus = MagicMock()
        bus.publish = AsyncMock()
        mock_bus.return_value = bus
        client = TestClient(_make_app())
        resp = client.post(
            "/api/v1/events/publish",
            json={
                "event_type": "run.started",
                "source": "test",
                "correlation_id": "corr-123",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_publish_validation_error(self):
        """Missing required event_type should return 422."""
        client = TestClient(_make_app())
        resp = client.post("/api/v1/events/publish", json={})
        assert resp.status_code == 422


class TestEventSchemas:
    """Test the Pydantic schemas used by events router."""

    def test_publish_request_defaults(self):
        from spine.api.routers.events import PublishEventRequest

        req = PublishEventRequest(event_type="test")
        assert req.source == "api"
        assert req.payload == {}
        assert req.correlation_id is None

    def test_status_response_defaults(self):
        from spine.api.routers.events import EventBusStatusResponse

        resp = EventBusStatusResponse()
        assert resp.backend == "unknown"
        assert resp.subscription_count == 0
        assert resp.closed is False

    def test_publish_response(self):
        from spine.api.routers.events import PublishEventResponse

        resp = PublishEventResponse(event_id="e-1", event_type="test.event")
        assert resp.success is True
        assert resp.event_id == "e-1"

    def test_recent_event_schema(self):
        from spine.api.routers.events import RecentEventSchema

        schema = RecentEventSchema(
            event_id="e-1",
            event_type="run.started",
            source="worker",
        )
        assert schema.event_id == "e-1"
        assert schema.payload == {}


class TestGlobMatch:
    """Test the _glob_match helper."""

    def test_exact_match(self):
        from spine.api.routers.events import _glob_match

        assert _glob_match("run.started", "run.started") is True

    def test_glob_star(self):
        from spine.api.routers.events import _glob_match

        assert _glob_match("run.started", "run.*") is True
        assert _glob_match("step.completed", "run.*") is False

    def test_glob_all(self):
        from spine.api.routers.events import _glob_match

        assert _glob_match("anything", "*") is True
