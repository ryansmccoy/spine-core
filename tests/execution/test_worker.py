"""
Tests for the background execution worker loop.

Exercises the full poll → claim → execute → complete/fail lifecycle
with an in-memory SQLite database and a simple handler registry.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import UTC, datetime

import pytest

from spine.execution.worker import WorkerLoop, WorkerInfo, WorkerStats, get_active_workers
from spine.execution.registry import HandlerRegistry


# ── Helpers ─────────────────────────────────────────────────────────────


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create the minimal execution tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS core_executions (
            id TEXT PRIMARY KEY,
            workflow TEXT,
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


def _insert_pending(conn: sqlite3.Connection, operation: str = "task:echo",
                     params: dict | None = None, run_id: str | None = None) -> str:
    """Insert a pending execution row and return its ID."""
    rid = run_id or str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO core_executions (id, workflow, params, status, created_at) "
        "VALUES (?, ?, ?, 'pending', ?)",
        (rid, operation, json.dumps(params or {}), now),
    )
    conn.commit()
    return rid


def _get_status(conn: sqlite3.Connection, run_id: str) -> str | None:
    cur = conn.execute("SELECT status FROM core_executions WHERE id = ?", (run_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _get_result(conn: sqlite3.Connection, run_id: str) -> str | None:
    cur = conn.execute("SELECT result FROM core_executions WHERE id = ?", (run_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _get_error(conn: sqlite3.Connection, run_id: str) -> str | None:
    cur = conn.execute("SELECT error FROM core_executions WHERE id = ?", (run_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _count_events(conn: sqlite3.Connection, run_id: str, event_type: str) -> int:
    cur = conn.execute(
        "SELECT COUNT(*) FROM core_execution_events WHERE execution_id = ? AND event_type = ?",
        (run_id, event_type),
    )
    return cur.fetchone()[0]


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def db():
    """In-memory SQLite with schema."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    _create_schema(conn)
    yield conn
    conn.close()


@pytest.fixture()
def registry():
    """Fresh handler registry with a simple echo handler."""
    reg = HandlerRegistry()
    reg.register("task", "echo", lambda p: {"echoed": p})
    reg.register("task", "slow", lambda p: (time.sleep(0.1), {"done": True})[1])
    reg.register("task", "fail", _failing_handler)
    return reg


def _failing_handler(params):
    raise RuntimeError("intentional failure")


@pytest.fixture()
def worker(db, registry):
    """Worker loop wired to test DB and registry."""
    w = WorkerLoop(
        conn=db,
        poll_interval=0.1,
        batch_size=5,
        max_workers=2,
        registry=registry,
        worker_id="test-worker",
    )
    return w


# ── Tests ────────────────────────────────────────────────────────────────


class TestWorkerPollAndExecute:
    """Core poll → execute → complete lifecycle."""

    def test_pending_run_gets_completed(self, db, worker):
        """A pending 'echo' task should transition to completed."""
        run_id = _insert_pending(db, "task:echo", {"msg": "hello"})

        # Run one poll cycle
        claimed = worker._poll()
        assert claimed == 1

        # Wait for thread pool to finish
        worker._pool.shutdown(wait=True)

        assert _get_status(db, run_id) == "completed"
        result = json.loads(_get_result(db, run_id))
        assert result["echoed"] == {"msg": "hello"}

    def test_failed_run_gets_marked_failed(self, db, worker):
        """A handler that throws should transition to failed."""
        run_id = _insert_pending(db, "task:fail")

        worker._poll()
        worker._pool.shutdown(wait=True)

        assert _get_status(db, run_id) == "failed"
        error = _get_error(db, run_id)
        assert "intentional failure" in error

    def test_missing_handler_fails_gracefully(self, db, worker):
        """A run for an unregistered handler should fail, not crash."""
        run_id = _insert_pending(db, "task:nonexistent")

        worker._poll()
        worker._pool.shutdown(wait=True)

        assert _get_status(db, run_id) == "failed"
        assert "No handler registered" in _get_error(db, run_id)

    def test_events_recorded(self, db, worker):
        """Both started and completed events should be recorded."""
        run_id = _insert_pending(db, "task:echo", {"x": 1})

        worker._poll()
        worker._pool.shutdown(wait=True)

        assert _count_events(db, run_id, "started") == 1
        assert _count_events(db, run_id, "completed") == 1

    def test_failed_events_recorded(self, db, worker):
        """Failed events should include started + failed."""
        run_id = _insert_pending(db, "task:fail")

        worker._poll()
        worker._pool.shutdown(wait=True)

        assert _count_events(db, run_id, "started") == 1
        assert _count_events(db, run_id, "failed") == 1

    def test_no_pending_returns_zero(self, db, worker):
        """Poll with no pending rows returns 0."""
        assert worker._poll() == 0

    def test_already_claimed_not_double_dispatched(self, db, worker):
        """A run claimed by another worker (status != pending) is skipped."""
        run_id = _insert_pending(db, "task:echo")

        # Manually mark as running (simulate another worker)
        db.execute(
            "UPDATE core_executions SET status = 'running' WHERE id = ?",
            (run_id,),
        )
        db.commit()

        # Our worker should claim 0
        assert worker._poll() == 0

    def test_batch_limit_respected(self, db, worker):
        """Worker batch_size caps how many runs are claimed per poll."""
        for _ in range(10):
            _insert_pending(db, "task:echo")

        claimed = worker._poll()
        assert claimed <= worker._batch_size

        worker._pool.shutdown(wait=True)

    def test_multiple_runs_all_complete(self, db, worker):
        """Multiple pending runs should all transition to completed."""
        ids = [_insert_pending(db, "task:echo", {"i": i}) for i in range(3)]

        worker._poll()
        worker._pool.shutdown(wait=True)

        for rid in ids:
            assert _get_status(db, rid) == "completed"


class TestWorkerStats:
    """Worker statistics tracking."""

    def test_stats_after_completion(self, db, worker):
        """Stats should reflect processed and completed counts."""
        _insert_pending(db, "task:echo")
        _insert_pending(db, "task:fail")

        worker._poll()
        worker._pool.shutdown(wait=True)

        stats = worker.get_stats()
        assert stats.total_processed == 2
        assert stats.total_completed == 1
        assert stats.total_failed == 1

    def test_worker_info(self, worker):
        """Worker info should have correct fields."""
        info = worker.info
        assert info.worker_id == "test-worker"
        assert info.status == "running"
        assert info.max_workers == 2


class TestWorkerLifecycle:
    """Worker start / stop / background."""

    def test_stop_terminates_loop(self, db, worker):
        """Calling stop() should cause the loop to exit."""
        t = worker.start_background()
        time.sleep(0.3)
        worker.stop()
        t.join(timeout=2)
        assert not t.is_alive()
        assert worker.info.status == "stopped"

    def test_background_worker_registers(self, db, worker):
        """A background worker should appear in get_active_workers()."""
        t = worker.start_background()
        time.sleep(0.3)

        try:
            workers = get_active_workers()
            ids = [w.worker_id for w in workers]
            assert "test-worker" in ids
        finally:
            worker.stop()
            t.join(timeout=2)

    def test_background_processes_runs(self, db, worker):
        """A background worker should process pending runs."""
        _insert_pending(db, "task:echo", {"val": 42})
        t = worker.start_background()

        # Wait for it to process
        time.sleep(1.0)

        try:
            status = _get_status(db, db.execute(
                "SELECT id FROM core_executions LIMIT 1"
            ).fetchone()[0])
            assert status == "completed"
        finally:
            worker.stop()
            t.join(timeout=2)


class TestWorkerKindParsing:
    """Test operation field parsing for kind:name format."""

    def test_kind_name_format(self, db, worker):
        """'task:echo' should resolve to kind=task, name=echo."""
        run_id = _insert_pending(db, "task:echo")
        worker._poll()
        worker._pool.shutdown(wait=True)
        assert _get_status(db, run_id) == "completed"

    def test_plain_name_defaults_to_task(self, db, worker):
        """A bare name like 'echo' should default to kind=task."""
        run_id = _insert_pending(db, "echo")
        worker._poll()
        worker._pool.shutdown(wait=True)
        assert _get_status(db, run_id) == "completed"
