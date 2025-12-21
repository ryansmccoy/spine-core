"""Tests for LockManager."""

from datetime import datetime, timedelta, UTC
import time

import pytest

from spine.core.scheduling import LockManager


class TestLockManager:
    """Test LockManager lock operations."""

    def test_acquire_lock(self, lock_manager):
        """Acquire schedule lock."""
        result = lock_manager.acquire_schedule_lock("schedule-1")
        assert result is True

    def test_acquire_lock_twice_same_instance(self, lock_manager):
        """Same instance can re-acquire its own lock (refresh)."""
        lock_manager.acquire_schedule_lock("schedule-2")
        result = lock_manager.acquire_schedule_lock("schedule-2")
        assert result is True

    def test_acquire_lock_different_instance(self, db_conn):
        """Different instance cannot acquire held lock."""
        manager1 = LockManager(db_conn, instance_id="instance-1")
        manager2 = LockManager(db_conn, instance_id="instance-2")

        result1 = manager1.acquire_schedule_lock("schedule-3")
        result2 = manager2.acquire_schedule_lock("schedule-3")

        assert result1 is True
        assert result2 is False

    def test_release_lock(self, lock_manager):
        """Release schedule lock."""
        lock_manager.acquire_schedule_lock("schedule-4")
        
        result = lock_manager.release_schedule_lock("schedule-4")
        assert result is True

        # Can now re-acquire
        result2 = lock_manager.acquire_schedule_lock("schedule-4")
        assert result2 is True

    def test_release_lock_not_held(self, lock_manager):
        """Release lock not held returns False."""
        result = lock_manager.release_schedule_lock("not-held")
        assert result is False

    def test_release_lock_held_by_other(self, db_conn):
        """Cannot release lock held by other instance."""
        manager1 = LockManager(db_conn, instance_id="instance-a")
        manager2 = LockManager(db_conn, instance_id="instance-b")

        manager1.acquire_schedule_lock("schedule-5")
        result = manager2.release_schedule_lock("schedule-5")

        assert result is False

    def test_is_locked(self, lock_manager):
        """Check if schedule is locked."""
        assert lock_manager.is_locked("schedule-6") is False

        lock_manager.acquire_schedule_lock("schedule-6")
        assert lock_manager.is_locked("schedule-6") is True

        lock_manager.release_schedule_lock("schedule-6")
        assert lock_manager.is_locked("schedule-6") is False

    def test_get_lock_holder(self, lock_manager):
        """Get instance holding the lock."""
        assert lock_manager.get_lock_holder("schedule-7") is None

        lock_manager.acquire_schedule_lock("schedule-7")
        holder = lock_manager.get_lock_holder("schedule-7")

        assert holder == lock_manager.instance_id


class TestLockManagerConcurrency:
    """Test LockManager concurrency locks."""

    def test_acquire_concurrency_lock(self, lock_manager):
        """Acquire general concurrency lock."""
        result = lock_manager.acquire_concurrency_lock("operation", "my-operation")
        assert result is True

    def test_release_concurrency_lock(self, lock_manager):
        """Release general concurrency lock."""
        lock_manager.acquire_concurrency_lock("operation", "my-operation")
        result = lock_manager.release_concurrency_lock("operation", "my-operation")
        assert result is True


class TestLockManagerExpiry:
    """Test LockManager lock expiry."""

    def test_expired_lock_can_be_acquired(self, db_conn):
        """Expired locks can be acquired by other instances."""
        manager1 = LockManager(db_conn, instance_id="instance-x")
        manager2 = LockManager(db_conn, instance_id="instance-y")

        # Acquire with very short TTL
        manager1.acquire_schedule_lock("schedule-8", ttl_seconds=1)

        # Wait for expiry
        time.sleep(1.5)

        # Other instance should be able to acquire
        result = manager2.acquire_schedule_lock("schedule-8")
        assert result is True

    def test_cleanup_expired_locks(self, db_conn, lock_manager):
        """Cleanup removes expired locks."""
        # Create a lock with short TTL
        lock_manager.acquire_schedule_lock("schedule-9", ttl_seconds=1)
        
        # Verify lock exists
        assert lock_manager.is_locked("schedule-9") is True

        # Wait for expiry
        time.sleep(1.5)

        # Cleanup
        count = lock_manager.cleanup_expired_locks()
        assert count >= 1

        # Lock should be gone
        assert lock_manager.is_locked("schedule-9") is False

    def test_list_active_locks(self, lock_manager):
        """List all active (non-expired) locks."""
        lock_manager.acquire_schedule_lock("active-1", ttl_seconds=300)
        lock_manager.acquire_schedule_lock("active-2", ttl_seconds=300)

        locks = lock_manager.list_active_locks()
        
        assert len(locks) >= 2
        lock_ids = [l["schedule_id"] for l in locks]
        assert "active-1" in lock_ids
        assert "active-2" in lock_ids

    def test_force_release_all(self, lock_manager):
        """Force release all locks."""
        lock_manager.acquire_schedule_lock("force-1")
        lock_manager.acquire_schedule_lock("force-2")
        lock_manager.acquire_schedule_lock("force-3")

        count = lock_manager.force_release_all()
        assert count >= 3

        assert lock_manager.is_locked("force-1") is False
        assert lock_manager.is_locked("force-2") is False
        assert lock_manager.is_locked("force-3") is False


class TestLockManagerInstanceId:
    """Test LockManager instance identification."""

    def test_auto_generated_instance_id(self, db_conn):
        """Instance ID is auto-generated if not provided."""
        manager = LockManager(db_conn)
        assert manager.instance_id is not None
        assert len(manager.instance_id) > 0

    def test_custom_instance_id(self, db_conn):
        """Custom instance ID is used."""
        manager = LockManager(db_conn, instance_id="my-custom-id")
        assert manager.instance_id == "my-custom-id"
