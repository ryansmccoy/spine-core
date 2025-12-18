"""End-to-end integration test: API submit → worker executes → query result.

Exercises the complete execution lifecycle:
1. Submit a run via ``POST /runs``
2. Background worker claims and executes it
3. Query the run status via ``GET /runs/{id}`` — should be completed
4. Verify events are recorded (submitted, started, completed)
5. Verify stats reflect the completed run
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid

import pytest

from spine.execution.registry import HandlerRegistry
from spine.execution.worker import WorkerLoop


# ── Helpers ──────────────────────────────────────────────────────────────


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create the execution tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS core_executions (
            id TEXT PRIMARY KEY,
            pipeline TEXT,
            params TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            lane TEXT DEFAULT 'default',
            trigger_source TEXT DEFAULT 'api',
            parent_execution_id TEXT,
            created_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,
            error TEXT,
            retry_count INTEGER DEFAULT 0,
            idempotency_key TEXT
        );
        CREATE TABLE IF NOT EXISTS core_execution_events (
            id TEXT PRIMARY KEY,
            execution_id TEXT,
            event_type TEXT,
            timestamp TEXT,
            data TEXT DEFAULT '{}'
        );
    """)


def _insert_pending(conn, pipeline, params=None, run_id=None):
    from datetime import UTC, datetime

    rid = run_id or str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO core_executions (id, pipeline, params, status, created_at, lane) "
        "VALUES (?, ?, ?, 'pending', ?, 'default')",
        (rid, pipeline, json.dumps(params or {}), now),
    )
    conn.commit()
    return rid


def _get_row(conn, run_id):
    cur = conn.execute("SELECT * FROM core_executions WHERE id = ?", (run_id,))
    row = cur.fetchone()
    if row is None:
        return None
    cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))


def _get_events(conn, run_id):
    cur = conn.execute(
        "SELECT event_type FROM core_execution_events WHERE execution_id = ? ORDER BY timestamp",
        (run_id,),
    )
    return [r[0] for r in cur.fetchall()]


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    _create_schema(conn)
    yield conn
    conn.close()


@pytest.fixture()
def registry():
    reg = HandlerRegistry()
    reg.register("task", "echo", lambda p: {"echoed": p})
    reg.register("task", "add", lambda p: {"result": p.get("a", 0) + p.get("b", 0)})
    reg.register("task", "fail", lambda _: (_ for _ in ()).throw(RuntimeError("test failure")))
    reg.register("task", "sleep", lambda p: (time.sleep(float(p.get("seconds", 0.1))), {"slept": True})[1])
    reg.register("pipeline", "etl_stub", lambda p: {"pipeline": "etl_stub", "records": p.get("records", 100)})
    return reg


@pytest.fixture()
def worker(db, registry):
    return WorkerLoop(
        conn=db,
        poll_interval=0.1,
        batch_size=10,
        max_workers=2,
        registry=registry,
        worker_id="e2e-worker",
    )


# ── Test class ───────────────────────────────────────────────────────────


class TestEndToEndWithWorker:
    """Full lifecycle: submit → worker → complete → query."""

    def test_echo_task_lifecycle(self, db, worker):
        """Submit echo → worker executes → status=completed, result has echoed params."""
        params = {"message": "hello world", "count": 42}
        run_id = _insert_pending(db, "task:echo", params)

        # Worker picks it up
        worker._poll()
        worker._pool.shutdown(wait=True)

        row = _get_row(db, run_id)
        assert row["status"] == "completed"
        result = json.loads(row["result"])
        assert result["echoed"] == params

        # Events: started + completed
        events = _get_events(db, run_id)
        assert "started" in events
        assert "completed" in events

    def test_add_task_computes_correctly(self, db, worker):
        """Submit add task → verify arithmetic result."""
        run_id = _insert_pending(db, "task:add", {"a": 17, "b": 25})

        worker._poll()
        worker._pool.shutdown(wait=True)

        row = _get_row(db, run_id)
        assert row["status"] == "completed"
        result = json.loads(row["result"])
        assert result["result"] == 42

    def test_pipeline_executes(self, db, worker):
        """Submit pipeline:etl_stub → completes with records count."""
        run_id = _insert_pending(db, "pipeline:etl_stub", {"records": 500})

        worker._poll()
        worker._pool.shutdown(wait=True)

        row = _get_row(db, run_id)
        assert row["status"] == "completed"
        result = json.loads(row["result"])
        assert result["records"] == 500

    def test_failed_task_records_error(self, db, worker):
        """Submit failing task → status=failed with error message."""
        run_id = _insert_pending(db, "task:fail")

        worker._poll()
        worker._pool.shutdown(wait=True)

        row = _get_row(db, run_id)
        assert row["status"] == "failed"
        assert "test failure" in row["error"]

        events = _get_events(db, run_id)
        assert "failed" in events

    def test_multiple_tasks_concurrent(self, db, worker):
        """Submit multiple tasks → all complete concurrently."""
        ids = [
            _insert_pending(db, "task:echo", {"i": i})
            for i in range(5)
        ]

        worker._poll()
        worker._pool.shutdown(wait=True)

        for rid in ids:
            assert _get_row(db, rid)["status"] == "completed"

    def test_mixed_success_and_failure(self, db, worker):
        """Mix of successful and failing tasks → each has correct status."""
        ok_id = _insert_pending(db, "task:echo", {"ok": True})
        fail_id = _insert_pending(db, "task:fail")
        add_id = _insert_pending(db, "task:add", {"a": 1, "b": 2})

        worker._poll()
        worker._pool.shutdown(wait=True)

        assert _get_row(db, ok_id)["status"] == "completed"
        assert _get_row(db, fail_id)["status"] == "failed"
        assert _get_row(db, add_id)["status"] == "completed"
        assert json.loads(_get_row(db, add_id)["result"])["result"] == 3

    def test_worker_stats_accurate(self, db, worker):
        """Worker stats reflect processed, completed, and failed counts."""
        _insert_pending(db, "task:echo")
        _insert_pending(db, "task:echo")
        _insert_pending(db, "task:fail")

        worker._poll()
        worker._pool.shutdown(wait=True)

        stats = worker.get_stats()
        assert stats.total_processed == 3
        assert stats.total_completed == 2
        assert stats.total_failed == 1

    def test_already_running_not_reclaimed(self, db, worker):
        """A running task should not be claimed again."""
        run_id = _insert_pending(db, "task:sleep", {"seconds": "5"})

        # Manually set to running (simulate another worker)
        db.execute("UPDATE core_executions SET status = 'running' WHERE id = ?", (run_id,))
        db.commit()

        assert worker._poll() == 0

    def test_completed_not_reclaimed(self, db, worker):
        """A completed task should not be claimed."""
        run_id = _insert_pending(db, "task:echo")
        db.execute("UPDATE core_executions SET status = 'completed' WHERE id = ?", (run_id,))
        db.commit()

        assert worker._poll() == 0


class TestEndToEndWithBackgroundWorker:
    """Full lifecycle with worker running in background thread."""

    def test_background_worker_processes_run(self, db, worker):
        """Submit a run, start worker in background → run completes."""
        run_id = _insert_pending(db, "task:echo", {"bg": True})

        t = worker.start_background()
        try:
            # Wait for processing
            for _ in range(30):
                row = _get_row(db, run_id)
                if row and row["status"] == "completed":
                    break
                time.sleep(0.1)

            row = _get_row(db, run_id)
            assert row["status"] == "completed"
            result = json.loads(row["result"])
            assert result["echoed"]["bg"] is True
        finally:
            worker.stop()
            t.join(timeout=3)

    def test_background_worker_processes_multiple(self, db, worker):
        """Submit runs over time → background worker picks them all up."""
        ids = []

        t = worker.start_background()
        try:
            # Submit in batches
            for i in range(3):
                rid = _insert_pending(db, "task:add", {"a": i, "b": i * 10})
                ids.append(rid)
                time.sleep(0.15)

            # Wait for all to complete
            for _ in range(50):
                all_done = all(
                    _get_row(db, rid)["status"] in ("completed", "failed")
                    for rid in ids
                )
                if all_done:
                    break
                time.sleep(0.1)

            for rid in ids:
                assert _get_row(db, rid)["status"] == "completed"
        finally:
            worker.stop()
            t.join(timeout=3)


class TestEndToEndViaAPI:
    """Test the full path through the FastAPI layer."""

    @pytest.fixture()
    def client(self, tmp_path):
        """TestClient with initialized DB."""
        from fastapi.testclient import TestClient
        from spine.api.app import create_app
        from spine.api.settings import SpineCoreAPISettings
        from spine.ops.context import OperationContext
        from spine.ops.requests import DatabaseInitRequest
        from spine.ops.sqlite_conn import SqliteConnection

        db_path = str(tmp_path / "e2e.db")
        settings = SpineCoreAPISettings(
            database_url=f"sqlite:///{db_path}",
            data_dir=str(tmp_path),
        )
        app = create_app(settings=settings)

        conn = SqliteConnection(db_path)
        ctx = OperationContext(conn=conn, caller="test")
        from spine.ops.database import initialize_database
        initialize_database(ctx, DatabaseInitRequest())

        with TestClient(app) as c:
            yield c

    def test_submit_via_api_creates_pending_run(self, client):
        """POST /runs creates a pending run with kind:name encoding."""
        resp = client.post("/api/v1/runs", json={
            "kind": "task",
            "name": "echo",
            "params": {"submitted": True},
        })
        assert resp.status_code == 202
        body = resp.json()
        assert body["data"]["run_id"] is not None

        # Verify it shows up in the list
        run_id = body["data"]["run_id"]
        detail = client.get(f"/api/v1/runs/{run_id}")
        assert detail.status_code == 200
        assert detail.json()["data"]["status"] == "pending"

    def test_submit_and_list_reflects_pending(self, client):
        """Multiple submits → list shows all as pending."""
        for i in range(3):
            client.post("/api/v1/runs", json={"kind": "task", "name": "echo", "params": {"i": i}})

        resp = client.get("/api/v1/runs?status=pending")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 3

    def test_stats_reflects_submitted_runs(self, client):
        """Stats endpoint counts submitted runs."""
        client.post("/api/v1/runs", json={"kind": "task", "name": "add", "params": {"a": 1, "b": 2}})

        resp = client.get("/api/v1/stats/runs")
        assert resp.status_code == 200
        stats = resp.json()["data"]
        assert stats["pending"] >= 1
        assert stats["total"] >= 1

    def test_submit_run_events_recorded(self, client):
        """Submit creates a 'submitted' event."""
        resp = client.post("/api/v1/runs", json={"kind": "task", "name": "echo"})
        run_id = resp.json()["data"]["run_id"]

        events_resp = client.get(f"/api/v1/runs/{run_id}/events")
        assert events_resp.status_code == 200
        events = events_resp.json()["data"]
        event_types = [e["event_type"] for e in events]
        assert "submitted" in event_types
