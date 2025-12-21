"""Tests for ExecutionRepository — analytics and maintenance queries."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from spine.execution.models import ExecutionStatus
from spine.execution.repository import ExecutionRepository


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def conn():
    """In-memory SQLite with executions + events tables."""
    db = sqlite3.connect(":memory:")
    db.execute("""
        CREATE TABLE core_executions (
            id TEXT PRIMARY KEY,
            workflow TEXT,
            params TEXT DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            lane TEXT DEFAULT 'default',
            trigger_source TEXT DEFAULT 'api',
            parent_execution_id TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,
            error TEXT,
            retry_count INTEGER DEFAULT 0,
            idempotency_key TEXT
        )
    """)
    db.execute("""
        CREATE TABLE core_execution_events (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            data TEXT DEFAULT '{}'
        )
    """)
    db.commit()
    yield db
    db.close()


@pytest.fixture()
def repo(conn):
    return ExecutionRepository(conn)


def _insert_execution(
    conn,
    *,
    exec_id: str,
    workflow: str = "test.pipe",
    status: str = "completed",
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    error: str | None = None,
    retry_count: int = 0,
    lane: str = "default",
):
    """Directly insert an execution row for test setup."""
    now = datetime.now(UTC)
    created = created_at or now
    conn.execute(
        """
        INSERT INTO core_executions
            (id, workflow, status, created_at, started_at, completed_at,
             error, retry_count, lane, trigger_source, params)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'api', '{}')
        """,
        (
            exec_id,
            workflow,
            status,
            created.isoformat(),
            started_at.isoformat() if started_at else None,
            completed_at.isoformat() if completed_at else None,
            error,
            retry_count,
            lane,
        ),
    )
    conn.commit()


# ── Stale Executions ─────────────────────────────────────────────────────


class TestStaleExecutions:
    def test_finds_stale(self, conn, repo):
        old = datetime.now(UTC) - timedelta(minutes=120)
        _insert_execution(
            conn, exec_id="e1", status="running",
            started_at=old, workflow="stuck.pipe",
        )
        stale = repo.get_stale_executions(older_than_minutes=60)
        assert len(stale) == 1
        assert stale[0]["id"] == "e1"

    def test_ignores_recent(self, conn, repo):
        recent = datetime.now(UTC) - timedelta(minutes=5)
        _insert_execution(
            conn, exec_id="e1", status="running",
            started_at=recent,
        )
        stale = repo.get_stale_executions(older_than_minutes=60)
        assert len(stale) == 0

    def test_ignores_completed(self, conn, repo):
        old = datetime.now(UTC) - timedelta(minutes=120)
        _insert_execution(
            conn, exec_id="e1", status="completed",
            started_at=old, completed_at=old + timedelta(minutes=5),
        )
        stale = repo.get_stale_executions(older_than_minutes=60)
        assert len(stale) == 0


# ── Execution Stats ─────────────────────────────────────────────────────


class TestExecutionStats:
    def test_status_counts(self, conn, repo):
        now = datetime.now(UTC)
        _insert_execution(conn, exec_id="e1", status="completed", created_at=now)
        _insert_execution(conn, exec_id="e2", status="completed", created_at=now)
        _insert_execution(conn, exec_id="e3", status="failed", created_at=now)
        stats = repo.get_execution_stats(hours=24)
        assert stats["status_counts"]["completed"] == 2
        assert stats["status_counts"]["failed"] == 1

    def test_avg_durations(self, conn, repo):
        now = datetime.now(UTC)
        t0 = now - timedelta(minutes=10)
        t1 = now - timedelta(minutes=5)
        _insert_execution(
            conn, exec_id="e1", status="completed",
            workflow="p1", created_at=t0,
            started_at=t0, completed_at=t0 + timedelta(seconds=10),
        )
        _insert_execution(
            conn, exec_id="e2", status="completed",
            workflow="p1", created_at=t1,
            started_at=t1, completed_at=t1 + timedelta(seconds=20),
        )
        stats = repo.get_execution_stats(hours=24)
        assert "p1" in stats["avg_duration_by_workflow"]
        assert stats["avg_duration_by_workflow"]["p1"] == pytest.approx(15.0)

    def test_empty_stats(self, repo):
        stats = repo.get_execution_stats(hours=24)
        assert stats["status_counts"] == {}
        assert stats["workflow_counts"] == {}


# ── Recent Failures ──────────────────────────────────────────────────────


class TestRecentFailures:
    def test_finds_failures(self, conn, repo):
        now = datetime.now(UTC)
        _insert_execution(
            conn, exec_id="e1", status="failed",
            created_at=now, completed_at=now, error="boom",
        )
        failures = repo.get_recent_failures(hours=24)
        assert len(failures) == 1
        assert failures[0]["error"] == "boom"

    def test_limit(self, conn, repo):
        now = datetime.now(UTC)
        for i in range(5):
            _insert_execution(
                conn, exec_id=f"e{i}", status="failed",
                created_at=now, completed_at=now, error=f"err{i}",
            )
        failures = repo.get_recent_failures(hours=24, limit=2)
        assert len(failures) == 2


# ── Cleanup ──────────────────────────────────────────────────────────────


class TestCleanup:
    def test_cleanup_old(self, conn, repo):
        old = datetime.now(UTC) - timedelta(days=100)
        recent = datetime.now(UTC) - timedelta(days=1)
        _insert_execution(conn, exec_id="old", created_at=old)
        _insert_execution(conn, exec_id="new", created_at=recent)
        deleted = repo.cleanup_old_executions(days=90)
        assert deleted == 1
        # Verify "new" still exists
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM core_executions")
        ids = [row[0] for row in cursor.fetchall()]
        assert "new" in ids
        assert "old" not in ids


# ── Operation Throughput ──────────────────────────────────────────────────


class TestOperationThroughput:
    def test_throughput(self, conn, repo):
        now = datetime.now(UTC)
        _insert_execution(
            conn, exec_id="e1", workflow="p1", status="completed",
            created_at=now, started_at=now,
            completed_at=now + timedelta(seconds=5),
        )
        _insert_execution(
            conn, exec_id="e2", workflow="p1", status="failed",
            created_at=now,
        )
        tp = repo.get_workflow_throughput("p1", hours=24)
        assert tp["workflow"] == "p1"
        assert tp["total"] == 2
        assert tp["completed"] == 1
        assert tp["failed"] == 1


# ── Queue Depth ──────────────────────────────────────────────────────────


class TestQueueDepth:
    def test_queue_depth(self, conn, repo):
        now = datetime.now(UTC)
        _insert_execution(
            conn, exec_id="e1", status="pending",
            created_at=now, lane="default",
        )
        _insert_execution(
            conn, exec_id="e2", status="queued",
            created_at=now, lane="gpu",
        )
        _insert_execution(
            conn, exec_id="e3", status="running",
            created_at=now,
        )
        depth = repo.get_queue_depth()
        assert depth.get("default", 0) == 1
        assert depth.get("gpu", 0) == 1

    def test_empty_queue(self, repo):
        depth = repo.get_queue_depth()
        assert depth == {}
