"""
Tests for the stats API router (/stats/*).

Exercises run statistics, queue depths, and worker info endpoints.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

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


def _seed_runs(tmp_path, statuses: list[str]) -> None:
    """Insert execution rows with given statuses."""
    import sqlite3

    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    now = datetime.now(UTC).isoformat()
    for status in statuses:
        conn.execute(
            "INSERT INTO core_executions (id, pipeline, status, created_at, lane) "
            "VALUES (?, 'task:test', ?, ?, 'default')",
            (str(uuid.uuid4()), status, now),
        )
    conn.commit()
    conn.close()


class TestRunStats:
    def test_stats_structure(self, client):
        resp = client.get("/api/v1/stats/runs")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Verify all expected keys exist
        for key in ("total", "pending", "running", "completed", "failed", "cancelled", "dead_lettered"):
            assert key in data
        assert isinstance(data["total"], int)
        assert data["total"] >= 0

    def test_stats_with_submitted_run(self, client):
        """After submitting a run via the API, pending count should increase."""
        # Get baseline
        resp1 = client.get("/api/v1/stats/runs")
        baseline_pending = resp1.json()["data"]["pending"]
        baseline_total = resp1.json()["data"]["total"]

        # Submit a new run
        client.post("/api/v1/runs", json={"kind": "task", "name": "test_run"})

        # Check counts increased
        resp2 = client.get("/api/v1/stats/runs")
        data = resp2.json()["data"]
        assert data["pending"] >= baseline_pending + 1
        assert data["total"] >= baseline_total + 1


class TestQueueDepths:
    def test_queues_structure(self, client):
        resp = client.get("/api/v1/stats/queues")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_queues_with_submitted_run(self, client):
        """After submitting a run, there should be at least one queue with pending."""
        client.post("/api/v1/runs", json={"kind": "task", "name": "queue_test"})
        resp = client.get("/api/v1/stats/queues")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Should have at least one lane with pending work
        total_pending = sum(q["pending"] for q in data)
        assert total_pending >= 1


class TestWorkerEndpoints:
    def test_no_workers(self, client):
        resp = client.get("/api/v1/stats/workers")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data == []

    def test_worker_stats_empty(self, client):
        resp = client.get("/api/v1/stats/workers/stats")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data == []
