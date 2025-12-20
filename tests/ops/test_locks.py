"""Tests for spine.ops.locks — concurrency lock and schedule lock operations."""

import pytest

from spine.core.schema_loader import apply_all_schemas
from spine.ops.database import initialize_database
from spine.ops.locks import (
    list_locks,
    list_schedule_locks,
    release_lock,
    release_schedule_lock,
)
from spine.ops.requests import ListScheduleLocksRequest


# ------------------------------------------------------------------ #
# Lock Test Helpers
# ------------------------------------------------------------------ #


def _insert_lock(
    ctx,
    lock_key="pipeline:finance-ingest",
    execution_id="exec_001",
):
    """Insert a concurrency lock row."""
    ctx.conn.execute(
        """
        INSERT INTO core_concurrency_locks (
            lock_key, execution_id, acquired_at, expires_at
        ) VALUES (?, ?, datetime('now'), datetime('now', '+5 minutes'))
        """,
        (lock_key, execution_id),
    )
    ctx.conn.commit()


def _insert_schedule_lock(
    ctx,
    schedule_id="sched_001",
    locked_by="scheduler_001",
):
    """Insert a schedule lock row."""
    ctx.conn.execute(
        """
        INSERT INTO core_schedule_locks (
            schedule_id, locked_by, locked_at, expires_at
        ) VALUES (?, ?, datetime('now'), datetime('now', '+5 minutes'))
        """,
        (schedule_id, locked_by),
    )
    ctx.conn.commit()


# ------------------------------------------------------------------ #
# List Locks Tests
# ------------------------------------------------------------------ #


class TestListLocks:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_locks(ctx)
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_lock(ctx)
        result = list_locks(ctx)
        assert result.success is True
        assert result.total == 1
        assert len(result.data) == 1
        assert result.data[0].lock_key == "pipeline:finance-ingest"
        assert result.data[0].owner == "exec_001"

    def test_multiple_locks(self, ctx):
        initialize_database(ctx)
        _insert_lock(ctx, lock_key="lock_1", execution_id="exec_1")
        _insert_lock(ctx, lock_key="lock_2", execution_id="exec_2")
        _insert_lock(ctx, lock_key="lock_3", execution_id="exec_3")

        result = list_locks(ctx)
        assert result.success is True
        assert result.total == 3


# ------------------------------------------------------------------ #
# Release Lock Tests
# ------------------------------------------------------------------ #


class TestReleaseLock:
    def test_validation_missing_key(self, ctx):
        initialize_database(ctx)
        result = release_lock(ctx, lock_key="")
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_release_existing_lock(self, ctx):
        initialize_database(ctx)
        _insert_lock(ctx, lock_key="test_lock")
        result = release_lock(ctx, lock_key="test_lock")
        assert result.success is True

        # Verify lock was released (no longer in list)
        list_result = list_locks(ctx)
        assert list_result.total == 0

    def test_release_nonexistent_lock(self, ctx):
        initialize_database(ctx)
        # Releasing a non-existent lock should succeed (idempotent)
        result = release_lock(ctx, lock_key="nonexistent")
        assert result.success is True

    def test_dry_run(self, dry_ctx):
        apply_all_schemas(dry_ctx.conn)
        _insert_lock(dry_ctx, lock_key="test_lock")
        result = release_lock(dry_ctx, lock_key="test_lock")
        assert result.success is True

        # Dry run should not release the lock
        list_result = list_locks(dry_ctx)
        assert list_result.total == 1


# ------------------------------------------------------------------ #
# List Schedule Locks Tests
# ------------------------------------------------------------------ #


class TestListScheduleLocks:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_schedule_locks(ctx, ListScheduleLocksRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        _insert_schedule_lock(ctx)
        result = list_schedule_locks(ctx, ListScheduleLocksRequest())
        assert result.success is True
        assert result.total == 1
        assert len(result.data) == 1
        assert result.data[0].schedule_id == "sched_001"
        assert result.data[0].locked_by == "scheduler_001"

    def test_multiple_locks(self, ctx):
        initialize_database(ctx)
        _insert_schedule_lock(ctx, schedule_id="sched_1", locked_by="scheduler_1")
        _insert_schedule_lock(ctx, schedule_id="sched_2", locked_by="scheduler_2")
        _insert_schedule_lock(ctx, schedule_id="sched_3", locked_by="scheduler_3")

        result = list_schedule_locks(ctx, ListScheduleLocksRequest())
        assert result.success is True
        assert result.total == 3

    def test_default_request(self, ctx):
        """Test that None request works (uses defaults)."""
        initialize_database(ctx)
        _insert_schedule_lock(ctx)
        result = list_schedule_locks(ctx, None)
        assert result.success is True
        assert result.total == 1


# ------------------------------------------------------------------ #
# Release Schedule Lock Tests
# ------------------------------------------------------------------ #


class TestReleaseScheduleLock:
    def test_validation_missing_id(self, ctx):
        initialize_database(ctx)
        result = release_schedule_lock(ctx, schedule_id="")
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_release_existing_lock(self, ctx):
        initialize_database(ctx)
        _insert_schedule_lock(ctx, schedule_id="sched_001")
        result = release_schedule_lock(ctx, schedule_id="sched_001")
        assert result.success is True

        # Verify lock was released
        list_result = list_schedule_locks(ctx, ListScheduleLocksRequest())
        assert list_result.total == 0

    def test_release_nonexistent_lock(self, ctx):
        initialize_database(ctx)
        # Releasing a non-existent lock should succeed (idempotent)
        result = release_schedule_lock(ctx, schedule_id="nonexistent")
        assert result.success is True

    def test_dry_run(self, dry_ctx):
        apply_all_schemas(dry_ctx.conn)
        _insert_schedule_lock(dry_ctx, schedule_id="sched_001")
        result = release_schedule_lock(dry_ctx, schedule_id="sched_001")
        assert result.success is True

        # Dry run should not release the lock
        list_result = list_schedule_locks(dry_ctx, ListScheduleLocksRequest())
        assert list_result.total == 1


# ------------------------------------------------------------------ #
# Edge Cases
# ------------------------------------------------------------------ #


class TestLockEdgeCases:
    def test_lock_with_special_characters_in_key(self, ctx):
        initialize_database(ctx)
        special_key = "pipeline:finance/Q1:2026-revenue"
        _insert_lock(ctx, lock_key=special_key)
        result = list_locks(ctx)
        assert result.success is True
        assert result.data[0].lock_key == special_key

        # Release should work too
        release_result = release_lock(ctx, lock_key=special_key)
        assert release_result.success is True

    def test_lock_with_long_execution_id(self, ctx):
        initialize_database(ctx)
        long_exec_id = "exec_" + "x" * 200
        _insert_lock(ctx, lock_key="test_lock", execution_id=long_exec_id)
        result = list_locks(ctx)
        assert result.success is True
        assert result.data[0].owner == long_exec_id

    def test_concurrent_schedule_locks_different_ids(self, ctx):
        initialize_database(ctx)
        # Insert many locks for different schedules
        for i in range(10):
            _insert_schedule_lock(ctx, schedule_id=f"sched_{i:03d}", locked_by=f"scheduler_{i}")

        result = list_schedule_locks(ctx, ListScheduleLocksRequest())
        assert result.success is True
        assert result.total == 10
