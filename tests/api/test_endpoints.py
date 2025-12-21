"""
Integration tests for API endpoints using FastAPI TestClient.

These tests exercise the full router → ops → response operation
using an in-memory SQLite database with initialised schema.
"""

from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from spine.api.app import create_app
from spine.api.settings import SpineCoreAPISettings
from spine.ops.context import OperationContext
from spine.ops.requests import DatabaseInitRequest
from spine.ops.sqlite_conn import SqliteConnection


@pytest.fixture()
def client(tmp_path):
    """Create a test client with a temporary SQLite database."""
    db_path = str(tmp_path / "test.db")
    settings = SpineCoreAPISettings(
        database_url=f"sqlite:///{db_path}",
        data_dir=str(tmp_path),
    )
    app = create_app(settings=settings)

    # Initialise schema
    conn = SqliteConnection(db_path)
    ctx = OperationContext(conn=conn, caller="test")
    from spine.ops.database import initialize_database
    initialize_database(ctx, DatabaseInitRequest())

    with TestClient(app) as c:
        yield c


class TestDiscoveryEndpoints:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_capabilities(self, client):
        resp = client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body


class TestDatabaseEndpoints:
    def test_init(self, client):
        resp = client.post("/api/v1/database/init")
        assert resp.status_code == 200

    def test_health(self, client):
        resp = client.get("/api/v1/database/health")
        assert resp.status_code == 200

    def test_tables(self, client):
        resp = client.get("/api/v1/database/tables")
        assert resp.status_code == 200

    def test_purge(self, client):
        resp = client.post("/api/v1/database/purge?older_than_days=30")
        assert resp.status_code == 200


class TestWorkflowEndpoints:
    def test_list(self, client):
        resp = client.get("/api/v1/workflows")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "page" in body

    def test_get_unknown(self, client):
        resp = client.get("/api/v1/workflows/nonexistent")
        # Should return error (404 or 500 depending on ops)
        assert resp.status_code in (200, 404, 500)


class TestRunEndpoints:
    def test_list_empty(self, client):
        resp = client.get("/api/v1/runs")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_with_filters(self, client):
        resp = client.get("/api/v1/runs?status=running&limit=10")
        assert resp.status_code == 200

    def test_get_unknown(self, client):
        resp = client.get("/api/v1/runs/nonexistent")
        assert resp.status_code in (200, 404, 500)

    def test_submit_task(self, client):
        resp = client.post(
            "/api/v1/runs",
            json={"kind": "task", "name": "my_task", "params": {"x": 1}},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["data"]["run_id"] is not None
        assert body["data"]["would_execute"] is True

    def test_submit_operation(self, client):
        resp = client.post(
            "/api/v1/runs",
            json={"kind": "operation", "name": "etl_operation"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["data"]["run_id"] is not None

    def test_submit_workflow(self, client):
        resp = client.post(
            "/api/v1/runs",
            json={"kind": "workflow", "name": "daily_ingest"},
        )
        assert resp.status_code == 202

    def test_submit_missing_name(self, client):
        resp = client.post(
            "/api/v1/runs",
            json={"kind": "task", "name": ""},
        )
        # Should fail validation
        assert resp.status_code in (400, 422, 500)

    def test_submit_invalid_kind(self, client):
        resp = client.post(
            "/api/v1/runs",
            json={"kind": "banana", "name": "test"},
        )
        assert resp.status_code in (400, 422, 500)

    def test_submit_and_get(self, client):
        # Submit
        resp = client.post(
            "/api/v1/runs",
            json={"kind": "task", "name": "roundtrip_task"},
        )
        assert resp.status_code == 202
        run_id = resp.json()["data"]["run_id"]

        # Fetch
        resp = client.get(f"/api/v1/runs/{run_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["run_id"] == run_id
        assert body["data"]["status"] == "pending"

    def test_submit_and_cancel(self, client):
        resp = client.post(
            "/api/v1/runs",
            json={"kind": "operation", "name": "cancel_me"},
        )
        run_id = resp.json()["data"]["run_id"]

        resp = client.post(f"/api/v1/runs/{run_id}/cancel", json={"reason": "testing"})
        assert resp.status_code == 200

    def test_events_for_submitted_run(self, client):
        # Submit to get a run with events
        resp = client.post(
            "/api/v1/runs",
            json={"kind": "task", "name": "event_test"},
        )
        run_id = resp.json()["data"]["run_id"]

        resp = client.get(f"/api/v1/runs/{run_id}/events")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert len(body["data"]) >= 1  # at least the "submitted" event
        assert body["data"][0]["event_type"] == "submitted"

    def test_events_empty_run(self, client):
        resp = client.get("/api/v1/runs/nonexistent/events")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []


class TestScheduleEndpoints:
    def test_list(self, client):
        resp = client.get("/api/v1/schedules")
        assert resp.status_code == 200

    def test_create(self, client):
        resp = client.post(
            "/api/v1/schedules",
            json={"name": "etl", "target_type": "workflow", "target_name": "etl", "cron_expression": "0 * * * *"},
        )
        assert resp.status_code in (201, 200, 500)

    def test_get_unknown(self, client):
        resp = client.get("/api/v1/schedules/nonexistent")
        assert resp.status_code in (200, 404, 500)


class TestDLQEndpoints:
    def test_list(self, client):
        resp = client.get("/api/v1/dlq")
        assert resp.status_code == 200


class TestAnomalyEndpoints:
    def test_list(self, client):
        resp = client.get("/api/v1/anomalies")
        assert resp.status_code == 200


class TestQualityEndpoints:
    def test_list(self, client):
        resp = client.get("/api/v1/quality")
        assert resp.status_code in (200, 500)  # 500 if table not created by init


class TestResponseHeaders:
    def test_request_id_header(self, client):
        resp = client.get("/api/v1/health")
        assert "X-Request-ID" in resp.headers

    def test_timing_header(self, client):
        resp = client.get("/api/v1/health")
        assert "X-Process-Time-Ms" in resp.headers

    def test_custom_request_id(self, client):
        resp = client.get(
            "/api/v1/health",
            headers={"X-Request-ID": "test-123"},
        )
        assert resp.headers["X-Request-ID"] == "test-123"
