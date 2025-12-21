"""Tests for spine.core.scheduling.lock_manager — Distributed lock management."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from spine.core.scheduling.lock_manager import LockManager


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def conn():
    """In-memory SQLite with core_schedule_locks table."""
    db = sqlite3.connect(":memory:")
    db.execute("""
        CREATE TABLE core_schedule_locks (
            schedule_id TEXT NOT NULL PRIMARY KEY,
            locked_by TEXT NOT NULL,
            locked_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    db.commit()
    yield db
    db.close()


@pytest.fixture()
def manager(conn):
    return LockManager(conn, instance_id="inst-1")


# ── Acquire / Release ───────────────────────────────────────────────────


class TestAcquireRelease:
    def test_acquire_succeeds(self, manager):
        assert manager.acquire_schedule_lock("sched-1") is True

    def test_acquire_twice_same_instance(self, manager):
        """Same instance can re-acquire (refresh) its own lock."""
        assert manager.acquire_schedule_lock("sched-1") is True
        assert manager.acquire_schedule_lock("sched-1") is True

    def test_acquire_blocked_by_other_instance(self, conn):
        m1 = LockManager(conn, instance_id="inst-1")
        m2 = LockManager(conn, instance_id="inst-2")

        assert m1.acquire_schedule_lock("sched-1") is True
        assert m2.acquire_schedule_lock("sched-1") is False

    def test_release_removes_lock(self, manager):
        manager.acquire_schedule_lock("sched-1")
        assert manager.release_schedule_lock("sched-1") is True

    def test_release_only_own_lock(self, conn):
        m1 = LockManager(conn, instance_id="inst-1")
        m2 = LockManager(conn, instance_id="inst-2")

        m1.acquire_schedule_lock("sched-1")
        assert m2.release_schedule_lock("sched-1") is False

    def test_release_after_release_returns_false(self, manager):
        manager.acquire_schedule_lock("sched-1")
        manager.release_schedule_lock("sched-1")
        assert manager.release_schedule_lock("sched-1") is False

    def test_release_enables_other_instance(self, conn):
        m1 = LockManager(conn, instance_id="inst-1")
        m2 = LockManager(conn, instance_id="inst-2")

        m1.acquire_schedule_lock("sched-1")
        m1.release_schedule_lock("sched-1")
        assert m2.acquire_schedule_lock("sched-1") is True


# ── Query Methods ────────────────────────────────────────────────────────


class TestQueryMethods:
    def test_is_locked_true(self, manager):
        manager.acquire_schedule_lock("sched-1")
        assert manager.is_locked("sched-1") is True

    def test_is_locked_false(self, manager):
        assert manager.is_locked("sched-1") is False

    def test_get_lock_holder(self, manager):
        manager.acquire_schedule_lock("sched-1")
        assert manager.get_lock_holder("sched-1") == "inst-1"

    def test_get_lock_holder_none(self, manager):
        assert manager.get_lock_holder("sched-1") is None


# ── Concurrency Locks ───────────────────────────────────────────────────


class TestConcurrencyLocks:
    def test_acquire_concurrency_lock(self, manager):
        assert manager.acquire_concurrency_lock("operation", "daily-report") is True

    def test_release_concurrency_lock(self, manager):
        manager.acquire_concurrency_lock("operation", "daily-report")
        assert manager.release_concurrency_lock("operation", "daily-report") is True

    def test_concurrency_uses_composite_key(self, conn):
        m1 = LockManager(conn, instance_id="inst-1")
        m2 = LockManager(conn, instance_id="inst-2")

        m1.acquire_concurrency_lock("operation", "report-a")
        # Different resource name should succeed
        assert m2.acquire_concurrency_lock("operation", "report-b") is True
        # Same resource name should fail
        assert m2.acquire_concurrency_lock("operation", "report-a") is False


# ── Maintenance ──────────────────────────────────────────────────────────


class TestMaintenance:
    def test_list_active_locks(self, manager):
        manager.acquire_schedule_lock("sched-1")
        manager.acquire_schedule_lock("sched-2")

        locks = manager.list_active_locks()
        assert len(locks) == 2
        ids = {l["schedule_id"] for l in locks}
        assert ids == {"sched-1", "sched-2"}

    def test_list_active_empty(self, manager):
        assert manager.list_active_locks() == []

    def test_force_release_all(self, manager):
        manager.acquire_schedule_lock("sched-1")
        manager.acquire_schedule_lock("sched-2")

        count = manager.force_release_all()
        assert count == 2
        assert manager.list_active_locks() == []

    def test_cleanup_expired_locks(self, conn):
        """Manually insert an expired lock and verify cleanup removes it."""
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        conn.execute(
            "INSERT INTO core_schedule_locks VALUES (?, ?, ?, ?)",
            ("sched-expired", "inst-old", past, past),
        )
        conn.commit()

        manager = LockManager(conn, instance_id="inst-1")
        count = manager.cleanup_expired_locks()
        assert count == 1
        assert manager.is_locked("sched-expired") is False

    def test_expired_lock_does_not_block(self, conn):
        """An expired lock should not prevent acquire."""
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        conn.execute(
            "INSERT INTO core_schedule_locks VALUES (?, ?, ?, ?)",
            ("sched-1", "inst-old", past, past),
        )
        conn.commit()

        manager = LockManager(conn, instance_id="inst-new")
        # Should succeed because old lock is expired
        assert manager.acquire_schedule_lock("sched-1") is True


# ── Multiple Schedules Isolation ─────────────────────────────────────────


class TestIsolation:
    def test_independent_schedules(self, manager):
        manager.acquire_schedule_lock("sched-1")
        manager.acquire_schedule_lock("sched-2")
        assert manager.is_locked("sched-1") is True
        assert manager.is_locked("sched-2") is True

        manager.release_schedule_lock("sched-1")
        assert manager.is_locked("sched-1") is False
        assert manager.is_locked("sched-2") is True
