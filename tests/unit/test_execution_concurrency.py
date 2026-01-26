"""Unit tests for spine.execution.concurrency module.

Tests ConcurrencyGuard locking behavior.
"""

import sqlite3
import pytest
from datetime import datetime, timezone, timedelta

from spine.core.schema import CORE_DDL
from spine.execution.concurrency import ConcurrencyGuard


@pytest.fixture
def conn():
    """Create in-memory SQLite database."""
    conn = sqlite3.connect(":memory:")
    for name, ddl in CORE_DDL.items():
        conn.execute(ddl)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def guard(conn):
    """Create ConcurrencyGuard instance."""
    return ConcurrencyGuard(conn)


class TestAcquire:
    """Test lock acquisition."""

    def test_acquire_new_lock(self, guard):
        """Can acquire a lock that doesn't exist."""
        result = guard.acquire("test.lock", "exec-123")
        assert result is True

    def test_acquire_creates_record(self, guard, conn):
        """Acquiring creates a database record."""
        guard.acquire("test.lock", "exec-123")
        
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM core_concurrency_locks WHERE lock_key = ?", ("test.lock",))
        row = cursor.fetchone()
        
        assert row is not None
        assert row[1] == "exec-123"  # execution_id

    def test_cannot_acquire_held_lock(self, guard):
        """Cannot acquire a lock held by another execution."""
        guard.acquire("test.lock", "exec-1")
        result = guard.acquire("test.lock", "exec-2")
        
        assert result is False

    def test_same_execution_can_reacquire(self, guard):
        """Same execution can re-acquire its own lock."""
        guard.acquire("test.lock", "exec-123")
        result = guard.acquire("test.lock", "exec-123")
        
        assert result is True

    def test_custom_timeout(self, guard, conn):
        """Timeout affects lock expiration."""
        guard.acquire("test.lock", "exec-123", timeout_seconds=60)
        
        cursor = conn.cursor()
        cursor.execute("SELECT expires_at FROM core_concurrency_locks WHERE lock_key = ?", ("test.lock",))
        expires_at_str = cursor.fetchone()[0]
        expires_at = datetime.fromisoformat(expires_at_str)
        
        # Should expire within ~60 seconds (allow some tolerance)
        now = datetime.now(timezone.utc)
        delta = (expires_at.replace(tzinfo=timezone.utc) - now).total_seconds()
        assert 55 <= delta <= 65


class TestRelease:
    """Test lock release."""

    def test_release_held_lock(self, guard):
        """Can release a lock we hold."""
        guard.acquire("test.lock", "exec-123")
        result = guard.release("test.lock", "exec-123")
        
        assert result is True
        assert guard.is_locked("test.lock") is False

    def test_release_without_execution_id(self, guard):
        """Can release lock without specifying execution ID."""
        guard.acquire("test.lock", "exec-123")
        result = guard.release("test.lock")
        
        assert result is True

    def test_release_nonexistent(self, guard):
        """Releasing nonexistent lock returns False."""
        result = guard.release("nonexistent.lock")
        assert result is False

    def test_release_wrong_execution(self, guard):
        """Cannot release lock owned by different execution."""
        guard.acquire("test.lock", "exec-1")
        result = guard.release("test.lock", "exec-2")
        
        assert result is False
        assert guard.is_locked("test.lock") is True


class TestIsLocked:
    """Test lock status checking."""

    def test_is_locked_true(self, guard):
        """Returns True for held lock."""
        guard.acquire("test.lock", "exec-123")
        assert guard.is_locked("test.lock") is True

    def test_is_locked_false_nonexistent(self, guard):
        """Returns False for nonexistent lock."""
        assert guard.is_locked("nonexistent") is False

    def test_is_locked_false_released(self, guard):
        """Returns False after lock is released."""
        guard.acquire("test.lock", "exec-123")
        guard.release("test.lock")
        
        assert guard.is_locked("test.lock") is False


class TestGetLockHolder:
    """Test getting lock holder."""

    def test_get_holder_returns_execution_id(self, guard):
        """Returns execution ID of lock holder."""
        guard.acquire("test.lock", "exec-123")
        holder = guard.get_lock_holder("test.lock")
        
        assert holder == "exec-123"

    def test_get_holder_none_for_unlocked(self, guard):
        """Returns None for unlocked key."""
        holder = guard.get_lock_holder("test.lock")
        assert holder is None


class TestExtendLock:
    """Test lock extension."""

    def test_extend_owned_lock(self, guard):
        """Can extend a lock we own."""
        guard.acquire("test.lock", "exec-123", timeout_seconds=60)
        result = guard.extend_lock("test.lock", "exec-123", timeout_seconds=3600)
        
        assert result is True

    def test_cannot_extend_unowned_lock(self, guard):
        """Cannot extend lock owned by another execution."""
        guard.acquire("test.lock", "exec-1")
        result = guard.extend_lock("test.lock", "exec-2", timeout_seconds=3600)
        
        assert result is False


class TestListActiveLocks:
    """Test listing active locks."""

    def test_list_multiple_locks(self, guard):
        """Lists all active locks."""
        guard.acquire("lock.a", "exec-1")
        guard.acquire("lock.b", "exec-2")
        guard.acquire("lock.c", "exec-3")
        
        locks = guard.list_active_locks()
        
        assert len(locks) == 3
        lock_keys = {lock["lock_key"] for lock in locks}
        assert lock_keys == {"lock.a", "lock.b", "lock.c"}

    def test_list_excludes_released(self, guard):
        """Released locks are not listed."""
        guard.acquire("lock.a", "exec-1")
        guard.acquire("lock.b", "exec-2")
        guard.release("lock.a")
        
        locks = guard.list_active_locks()
        lock_keys = {lock["lock_key"] for lock in locks}
        
        assert lock_keys == {"lock.b"}


class TestCleanupExpired:
    """Test expired lock cleanup."""

    def test_cleanup_removes_expired(self, guard, conn):
        """Cleanup removes expired locks."""
        # Create an expired lock manually
        cursor = conn.cursor()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        cursor.execute(
            "INSERT INTO core_concurrency_locks VALUES (?, ?, ?, ?)",
            ("expired.lock", "old-exec", past, past),
        )
        conn.commit()
        
        count = guard.cleanup_expired()
        
        assert count == 1
        assert guard.is_locked("expired.lock") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
