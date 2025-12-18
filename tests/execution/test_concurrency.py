"""Tests for ConcurrencyGuard — DB-level locking to prevent duplicate runs."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from spine.execution.concurrency import ConcurrencyGuard


# ── Helpers ──────────────────────────────────────────────────────────────


@pytest.fixture()
def conn():
    """In-memory SQLite with concurrency_locks table."""
    db = sqlite3.connect(":memory:")
    db.execute("""
        CREATE TABLE core_concurrency_locks (
            lock_key TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    db.commit()
    yield db
    db.close()


@pytest.fixture()
def guard(conn):
    return ConcurrencyGuard(conn)


# ── Acquire / Release ────────────────────────────────────────────────────


class TestAcquireRelease:
    """Basic lock acquire and release."""

    def test_acquire_succeeds(self, guard):
        assert guard.acquire("p:1", execution_id="e1") is True

    def test_acquire_same_key_blocked(self, guard):
        guard.acquire("p:1", execution_id="e1")
        assert guard.acquire("p:1", execution_id="e2") is False

    def test_release_frees_lock(self, guard):
        guard.acquire("p:1", execution_id="e1")
        assert guard.release("p:1") is True
        # Should be acquirable again
        assert guard.acquire("p:1", execution_id="e2") is True

    def test_release_with_owner(self, guard):
        guard.acquire("p:1", execution_id="e1")
        # Wrong owner — should still delete (no owner check on lock_key-only release)
        assert guard.release("p:1", execution_id="e1") is True
        assert guard.is_locked("p:1") is False

    def test_release_wrong_owner(self, guard):
        guard.acquire("p:1", execution_id="e1")
        # Release with wrong execution_id
        assert guard.release("p:1", execution_id="e2") is False
        assert guard.is_locked("p:1") is True

    def test_release_nonexistent(self, guard):
        assert guard.release("nonexistent") is False

    def test_reentrant_lock(self, guard):
        """Same execution_id can re-acquire (extend) its own lock."""
        guard.acquire("p:1", execution_id="e1")
        assert guard.acquire("p:1", execution_id="e1") is True


# ── Expiry ───────────────────────────────────────────────────────────────


class TestExpiry:
    """Lock expiry and cleanup."""

    def test_expired_lock_not_visible(self, guard):
        """An expired lock should not show as locked."""
        guard.acquire("p:1", execution_id="e1", timeout_seconds=1)
        # Force time forward
        past = datetime.now(UTC) + timedelta(seconds=2)
        with patch("spine.execution.concurrency.utcnow", return_value=past):
            assert guard.is_locked("p:1") is False

    def test_expired_lock_cleaned_on_acquire(self, guard):
        """Acquiring should clean up expired locks first."""
        guard.acquire("p:1", execution_id="e1", timeout_seconds=1)
        past = datetime.now(UTC) + timedelta(seconds=2)
        with patch("spine.execution.concurrency.utcnow", return_value=past):
            assert guard.acquire("p:1", execution_id="e2") is True

    def test_cleanup_expired(self, guard):
        guard.acquire("p:1", execution_id="e1", timeout_seconds=1)
        guard.acquire("p:2", execution_id="e2", timeout_seconds=1)
        guard.acquire("p:3", execution_id="e3", timeout_seconds=9999)
        past = datetime.now(UTC) + timedelta(seconds=2)
        with patch("spine.execution.concurrency.utcnow", return_value=past):
            cleaned = guard.cleanup_expired()
        assert cleaned == 2


# ── Query ────────────────────────────────────────────────────────────────


class TestQuery:
    """Lock query methods."""

    def test_is_locked(self, guard):
        assert guard.is_locked("p:1") is False
        guard.acquire("p:1", execution_id="e1")
        assert guard.is_locked("p:1") is True

    def test_get_lock_holder(self, guard):
        assert guard.get_lock_holder("p:1") is None
        guard.acquire("p:1", execution_id="e1")
        assert guard.get_lock_holder("p:1") == "e1"

    def test_get_lock_holder_expired(self, guard):
        guard.acquire("p:1", execution_id="e1", timeout_seconds=1)
        past = datetime.now(UTC) + timedelta(seconds=2)
        with patch("spine.execution.concurrency.utcnow", return_value=past):
            assert guard.get_lock_holder("p:1") is None

    def test_list_active_locks(self, guard):
        guard.acquire("p:1", execution_id="e1")
        guard.acquire("p:2", execution_id="e2")
        locks = guard.list_active_locks()
        keys = {lock["lock_key"] for lock in locks}
        assert keys == {"p:1", "p:2"}


# ── Extend ───────────────────────────────────────────────────────────────


class TestExtendLock:
    def test_extend_own_lock(self, guard):
        guard.acquire("p:1", execution_id="e1", timeout_seconds=10)
        assert guard.extend_lock("p:1", "e1", timeout_seconds=9999) is True

    def test_extend_wrong_owner(self, guard):
        guard.acquire("p:1", execution_id="e1")
        assert guard.extend_lock("p:1", "e2") is False

    def test_extend_nonexistent(self, guard):
        assert guard.extend_lock("p:1", "e1") is False
