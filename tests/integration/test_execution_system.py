"""Integration test for the complete execution system.

This test exercises ALL execution infrastructure components:
- ExecutionLedger (create, update, list executions)
- ExecutionEvent recording
- ConcurrencyGuard (acquire, release, expiry)
- DLQManager (add, retry, resolve)
- ExecutionRepository (stats, stale detection, cleanup)

Uses SQLite in-memory database for isolation.
"""

import sqlite3
import time
from datetime import datetime, timedelta, timezone
import pytest

from spine.core.schema import CORE_DDL
from spine.execution.models import (
    Execution,
    ExecutionStatus,
    EventType,
    TriggerSource,
)
from spine.execution.ledger import ExecutionLedger
from spine.execution.concurrency import ConcurrencyGuard
from spine.execution.dlq import DLQManager
from spine.execution.repository import ExecutionRepository


@pytest.fixture
def conn():
    """Create in-memory SQLite database with all tables."""
    conn = sqlite3.connect(":memory:")
    
    # Create all core tables
    for name, ddl in CORE_DDL.items():
        conn.execute(ddl)
    conn.commit()
    
    yield conn
    conn.close()


class TestExecutionLedger:
    """Test ExecutionLedger CRUD operations."""

    def test_create_and_get_execution(self, conn):
        """Create an execution and retrieve it."""
        ledger = ExecutionLedger(conn)
        
        # Create execution
        execution = Execution.create(
            pipeline="finra.otc.ingest",
            params={"week_ending": "2025-01-09", "tier": "NMS_TIER_1"},
            lane="default",
            trigger_source=TriggerSource.CLI,
        )
        
        created = ledger.create_execution(execution)
        assert created.id == execution.id
        assert created.status == ExecutionStatus.PENDING
        
        # Retrieve it
        retrieved = ledger.get_execution(execution.id)
        assert retrieved is not None
        assert retrieved.pipeline == "finra.otc.ingest"
        assert retrieved.params["week_ending"] == "2025-01-09"
        assert retrieved.trigger_source == TriggerSource.CLI

    def test_update_status_lifecycle(self, conn):
        """Test full execution lifecycle: PENDING → RUNNING → COMPLETED."""
        ledger = ExecutionLedger(conn)
        
        execution = Execution.create(pipeline="test.pipeline")
        ledger.create_execution(execution)
        
        # Start execution
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        running = ledger.get_execution(execution.id)
        assert running.status == ExecutionStatus.RUNNING
        assert running.started_at is not None
        
        # Complete execution
        ledger.update_status(
            execution.id,
            ExecutionStatus.COMPLETED,
            result={"rows_processed": 1000},
        )
        completed = ledger.get_execution(execution.id)
        assert completed.status == ExecutionStatus.COMPLETED
        assert completed.completed_at is not None
        assert completed.result["rows_processed"] == 1000

    def test_update_status_failure(self, conn):
        """Test execution failure with error message."""
        ledger = ExecutionLedger(conn)
        
        execution = Execution.create(pipeline="test.pipeline")
        ledger.create_execution(execution)
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        
        # Fail execution
        ledger.update_status(
            execution.id,
            ExecutionStatus.FAILED,
            error="Connection timeout after 30s",
        )
        
        failed = ledger.get_execution(execution.id)
        assert failed.status == ExecutionStatus.FAILED
        assert "timeout" in failed.error.lower()

    def test_idempotency_key(self, conn):
        """Test finding execution by idempotency key."""
        ledger = ExecutionLedger(conn)
        
        execution = Execution.create(
            pipeline="finra.otc.ingest",
            params={"week_ending": "2025-01-09"},
            idempotency_key="finra.otc:2025-01-09",
        )
        ledger.create_execution(execution)
        
        # Find by idempotency key
        found = ledger.get_by_idempotency_key("finra.otc:2025-01-09")
        assert found is not None
        assert found.id == execution.id
        
        # Non-existent key returns None
        not_found = ledger.get_by_idempotency_key("does-not-exist")
        assert not_found is None

    def test_list_executions_with_filters(self, conn):
        """Test listing executions with various filters."""
        ledger = ExecutionLedger(conn)
        
        # Create mix of executions
        for i in range(5):
            exec1 = Execution.create(pipeline="pipeline.a")
            ledger.create_execution(exec1)
            
            exec2 = Execution.create(pipeline="pipeline.b")
            ledger.create_execution(exec2)
            ledger.update_status(exec2.id, ExecutionStatus.COMPLETED)
        
        # List all
        all_execs = ledger.list_executions(limit=100)
        assert len(all_execs) == 10
        
        # Filter by pipeline
        pipeline_a = ledger.list_executions(pipeline="pipeline.a")
        assert len(pipeline_a) == 5
        assert all(e.pipeline == "pipeline.a" for e in pipeline_a)
        
        # Filter by status
        completed = ledger.list_executions(status=ExecutionStatus.COMPLETED)
        assert len(completed) == 5
        assert all(e.status == ExecutionStatus.COMPLETED for e in completed)

    def test_events_recorded(self, conn):
        """Test that events are recorded for lifecycle changes."""
        ledger = ExecutionLedger(conn)
        
        execution = Execution.create(pipeline="test.pipeline")
        ledger.create_execution(execution)
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        ledger.update_status(execution.id, ExecutionStatus.COMPLETED, result={"ok": True})
        
        events = ledger.get_events(execution.id)
        assert len(events) >= 3  # CREATED, RUNNING, COMPLETED
        
        event_types = [e.event_type for e in events]
        assert EventType.CREATED in event_types
        assert EventType.STARTED in event_types
        assert EventType.COMPLETED in event_types

    def test_increment_retry(self, conn):
        """Test incrementing retry count."""
        ledger = ExecutionLedger(conn)
        
        execution = Execution.create(pipeline="test.pipeline")
        ledger.create_execution(execution)
        
        assert ledger.get_execution(execution.id).retry_count == 0
        
        count = ledger.increment_retry(execution.id)
        assert count == 1
        
        count = ledger.increment_retry(execution.id)
        assert count == 2
        
        assert ledger.get_execution(execution.id).retry_count == 2


class TestConcurrencyGuard:
    """Test ConcurrencyGuard locking behavior."""

    def test_acquire_and_release(self, conn):
        """Basic acquire and release flow."""
        guard = ConcurrencyGuard(conn)
        
        lock_key = "finra.otc.ingest:2025-01-09"
        exec_id = "exec-123"
        
        # Acquire lock
        assert guard.acquire(lock_key, exec_id) is True
        assert guard.is_locked(lock_key) is True
        assert guard.get_lock_holder(lock_key) == exec_id
        
        # Release lock
        assert guard.release(lock_key, exec_id) is True
        assert guard.is_locked(lock_key) is False
        assert guard.get_lock_holder(lock_key) is None

    def test_lock_prevents_double_acquisition(self, conn):
        """Second execution cannot acquire held lock."""
        guard = ConcurrencyGuard(conn)
        
        lock_key = "finra.otc.ingest:2025-01-09"
        
        # First execution acquires
        assert guard.acquire(lock_key, "exec-1") is True
        
        # Second execution cannot acquire
        assert guard.acquire(lock_key, "exec-2") is False
        
        # Lock holder is still first execution
        assert guard.get_lock_holder(lock_key) == "exec-1"

    def test_same_execution_can_reacquire(self, conn):
        """Same execution can re-acquire its own lock."""
        guard = ConcurrencyGuard(conn)
        
        lock_key = "test.lock"
        exec_id = "exec-123"
        
        assert guard.acquire(lock_key, exec_id) is True
        assert guard.acquire(lock_key, exec_id) is True  # Re-acquire OK
        assert guard.get_lock_holder(lock_key) == exec_id

    def test_extend_lock(self, conn):
        """Test extending a lock's expiration."""
        guard = ConcurrencyGuard(conn)
        
        lock_key = "test.lock"
        exec_id = "exec-123"
        
        guard.acquire(lock_key, exec_id, timeout_seconds=60)
        
        # Extend the lock
        assert guard.extend_lock(lock_key, exec_id, timeout_seconds=3600) is True
        
        # Cannot extend a lock we don't own
        assert guard.extend_lock(lock_key, "other-exec", timeout_seconds=3600) is False

    def test_list_active_locks(self, conn):
        """Test listing all active locks."""
        guard = ConcurrencyGuard(conn)
        
        guard.acquire("lock.a", "exec-1")
        guard.acquire("lock.b", "exec-2")
        guard.acquire("lock.c", "exec-3")
        
        locks = guard.list_active_locks()
        assert len(locks) == 3
        
        lock_keys = {lock["lock_key"] for lock in locks}
        assert lock_keys == {"lock.a", "lock.b", "lock.c"}


class TestDLQManager:
    """Test DLQManager dead letter queue operations."""

    def test_add_and_get(self, conn):
        """Add a dead letter and retrieve it."""
        dlq = DLQManager(conn)
        
        entry = dlq.add_to_dlq(
            execution_id="exec-123",
            pipeline="finra.otc.ingest",
            params={"week_ending": "2025-01-09"},
            error="Connection timeout",
            retry_count=3,
        )
        
        assert entry.id is not None
        assert entry.pipeline == "finra.otc.ingest"
        assert entry.error == "Connection timeout"
        
        # Retrieve it
        retrieved = dlq.get(entry.id)
        assert retrieved is not None
        assert retrieved.execution_id == "exec-123"

    def test_list_unresolved(self, conn):
        """Test listing unresolved entries."""
        dlq = DLQManager(conn)
        
        # Add some entries
        dlq.add_to_dlq("exec-1", "pipeline.a", {}, "Error 1")
        dlq.add_to_dlq("exec-2", "pipeline.a", {}, "Error 2")
        entry3 = dlq.add_to_dlq("exec-3", "pipeline.b", {}, "Error 3")
        
        # Resolve one
        dlq.resolve(entry3.id, resolved_by="user@example.com")
        
        # List unresolved
        unresolved = dlq.list_unresolved()
        assert len(unresolved) == 2
        
        # Filter by pipeline
        unresolved_a = dlq.list_unresolved(pipeline="pipeline.a")
        assert len(unresolved_a) == 2

    def test_resolve(self, conn):
        """Test resolving a dead letter."""
        dlq = DLQManager(conn)
        
        entry = dlq.add_to_dlq("exec-123", "test.pipeline", {}, "Error")
        
        assert dlq.resolve(entry.id, resolved_by="admin") is True
        
        resolved = dlq.get(entry.id)
        assert resolved.resolved_at is not None
        assert resolved.resolved_by == "admin"
        
        # Cannot resolve again
        assert dlq.resolve(entry.id) is False

    def test_can_retry(self, conn):
        """Test retry eligibility check."""
        dlq = DLQManager(conn, max_retries=3)
        
        entry = dlq.add_to_dlq(
            "exec-123", "test.pipeline", {}, "Error",
            retry_count=2, max_retries=3,
        )
        
        # Can retry (2 < 3)
        assert dlq.can_retry(entry.id) is True
        
        # Mark retry attempted
        dlq.mark_retry_attempted(entry.id)
        
        # Cannot retry (3 >= 3)
        assert dlq.can_retry(entry.id) is False

    def test_count_unresolved(self, conn):
        """Test counting unresolved entries."""
        dlq = DLQManager(conn)
        
        dlq.add_to_dlq("exec-1", "pipeline.a", {}, "Error 1")
        dlq.add_to_dlq("exec-2", "pipeline.a", {}, "Error 2")
        dlq.add_to_dlq("exec-3", "pipeline.b", {}, "Error 3")
        
        assert dlq.count_unresolved() == 3
        assert dlq.count_unresolved(pipeline="pipeline.a") == 2


class TestExecutionRepository:
    """Test ExecutionRepository analytics queries."""

    def test_get_execution_stats(self, conn):
        """Test getting execution statistics."""
        ledger = ExecutionLedger(conn)
        repo = ExecutionRepository(conn)
        
        # Create some executions
        for i in range(5):
            exec1 = Execution.create(pipeline="pipeline.a")
            ledger.create_execution(exec1)
            ledger.update_status(exec1.id, ExecutionStatus.RUNNING)
            ledger.update_status(exec1.id, ExecutionStatus.COMPLETED, result={})
        
        for i in range(3):
            exec2 = Execution.create(pipeline="pipeline.b")
            ledger.create_execution(exec2)
            ledger.update_status(exec2.id, ExecutionStatus.RUNNING)
            ledger.update_status(exec2.id, ExecutionStatus.FAILED, error="Error")
        
        stats = repo.get_execution_stats(hours=24)
        
        assert stats["status_counts"]["completed"] == 5
        assert stats["status_counts"]["failed"] == 3
        assert stats["pipeline_counts"]["pipeline.a"] == 5
        assert stats["pipeline_counts"]["pipeline.b"] == 3

    def test_get_stale_executions(self, conn):
        """Test finding stale/stuck executions."""
        ledger = ExecutionLedger(conn)
        repo = ExecutionRepository(conn)
        
        # Create and start an execution
        execution = Execution.create(pipeline="test.pipeline")
        ledger.create_execution(execution)
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        
        # Manually backdate started_at to simulate stale execution
        conn.execute(
            "UPDATE core_executions SET started_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(), execution.id),
        )
        conn.commit()
        
        # Find stale executions (running > 60 min)
        stale = repo.get_stale_executions(older_than_minutes=60)
        assert len(stale) == 1
        assert stale[0]["id"] == execution.id

    def test_get_recent_failures(self, conn):
        """Test getting recent failures."""
        ledger = ExecutionLedger(conn)
        repo = ExecutionRepository(conn)
        
        # Create some failures
        for i in range(5):
            execution = Execution.create(pipeline="failing.pipeline")
            ledger.create_execution(execution)
            ledger.update_status(execution.id, ExecutionStatus.RUNNING)
            ledger.update_status(
                execution.id,
                ExecutionStatus.FAILED,
                error=f"Error {i}",
            )
        
        failures = repo.get_recent_failures(hours=24, limit=10)
        assert len(failures) == 5
        assert all(f["pipeline"] == "failing.pipeline" for f in failures)

    def test_get_pipeline_throughput(self, conn):
        """Test getting pipeline-specific throughput metrics."""
        ledger = ExecutionLedger(conn)
        repo = ExecutionRepository(conn)
        
        # Create executions for one pipeline
        for i in range(10):
            execution = Execution.create(pipeline="target.pipeline")
            ledger.create_execution(execution)
            ledger.update_status(execution.id, ExecutionStatus.RUNNING)
            if i < 8:
                ledger.update_status(execution.id, ExecutionStatus.COMPLETED, result={})
            else:
                ledger.update_status(execution.id, ExecutionStatus.FAILED, error="Error")
        
        throughput = repo.get_pipeline_throughput("target.pipeline", hours=24)
        
        assert throughput["total"] == 10
        assert throughput["completed"] == 8
        assert throughput["failed"] == 2

    def test_get_queue_depth(self, conn):
        """Test getting queue depth by lane."""
        ledger = ExecutionLedger(conn)
        repo = ExecutionRepository(conn)
        
        # Create pending executions in different lanes
        for i in range(3):
            execution = Execution.create(pipeline="test.pipeline", lane="fast")
            ledger.create_execution(execution)
        
        for i in range(5):
            execution = Execution.create(pipeline="test.pipeline", lane="slow")
            ledger.create_execution(execution)
        
        # Start one to remove from queue
        started = Execution.create(pipeline="test.pipeline", lane="fast")
        ledger.create_execution(started)
        ledger.update_status(started.id, ExecutionStatus.RUNNING)
        
        depth = repo.get_queue_depth()
        assert depth["fast"] == 3
        assert depth["slow"] == 5


class TestEndToEndScenario:
    """Integration test covering a complete workflow scenario."""

    def test_full_execution_lifecycle_with_failure_and_dlq(self, conn):
        """
        Complete scenario:
        1. Submit execution with concurrency lock
        2. Execution fails
        3. Add to DLQ
        4. Retry from DLQ
        5. Second attempt succeeds
        6. Verify all records and events
        """
        ledger = ExecutionLedger(conn)
        guard = ConcurrencyGuard(conn)
        dlq = DLQManager(conn, max_retries=3)
        repo = ExecutionRepository(conn)
        
        pipeline = "finra.otc.ingest"
        params = {"week_ending": "2025-01-09", "tier": "NMS_TIER_1"}
        lock_key = f"{pipeline}:2025-01-09:NMS_TIER_1"
        
        # === FIRST ATTEMPT (fails) ===
        
        # Create execution
        exec1 = Execution.create(
            pipeline=pipeline,
            params=params,
            trigger_source=TriggerSource.CLI,
            idempotency_key=lock_key,
        )
        ledger.create_execution(exec1)
        
        # Acquire lock
        assert guard.acquire(lock_key, exec1.id) is True
        
        # Start execution
        ledger.update_status(exec1.id, ExecutionStatus.RUNNING)
        
        # Simulate failure
        error_msg = "Database connection lost during batch insert"
        ledger.update_status(exec1.id, ExecutionStatus.FAILED, error=error_msg)
        
        # Release lock
        guard.release(lock_key, exec1.id)
        
        # Add to DLQ
        dlq_entry = dlq.add_to_dlq(
            execution_id=exec1.id,
            pipeline=pipeline,
            params=params,
            error=error_msg,
            retry_count=0,
        )
        
        # Verify state after first attempt
        failed_exec = ledger.get_execution(exec1.id)
        assert failed_exec.status == ExecutionStatus.FAILED
        assert dlq.count_unresolved() == 1
        
        # === SECOND ATTEMPT (succeeds) ===
        
        # Create new execution for retry
        exec2 = Execution.create(
            pipeline=pipeline,
            params=params,
            trigger_source=TriggerSource.RETRY,
            parent_execution_id=exec1.id,
        )
        ledger.create_execution(exec2)
        
        # Acquire lock
        assert guard.acquire(lock_key, exec2.id) is True
        
        # Mark retry attempted on DLQ
        dlq.mark_retry_attempted(dlq_entry.id)
        
        # Run execution
        ledger.update_status(exec2.id, ExecutionStatus.RUNNING)
        ledger.update_status(
            exec2.id,
            ExecutionStatus.COMPLETED,
            result={"rows_processed": 15000, "duration_seconds": 45.2},
        )
        
        # Release lock
        guard.release(lock_key, exec2.id)
        
        # Resolve DLQ entry
        dlq.resolve(dlq_entry.id, resolved_by="retry-system")
        
        # === VERIFY FINAL STATE ===
        
        # First execution still shows as failed
        failed = ledger.get_execution(exec1.id)
        assert failed.status == ExecutionStatus.FAILED
        
        # Second execution completed
        completed = ledger.get_execution(exec2.id)
        assert completed.status == ExecutionStatus.COMPLETED
        assert completed.result["rows_processed"] == 15000
        assert completed.parent_execution_id == exec1.id
        
        # DLQ entry resolved
        resolved_dlq = dlq.get(dlq_entry.id)
        assert resolved_dlq.resolved_at is not None
        assert resolved_dlq.resolved_by == "retry-system"
        
        # No unresolved DLQ entries
        assert dlq.count_unresolved() == 0
        
        # Check events were recorded
        exec1_events = ledger.get_events(exec1.id)
        assert len(exec1_events) >= 3  # CREATED, STARTED, FAILED
        
        exec2_events = ledger.get_events(exec2.id)
        assert len(exec2_events) >= 3  # CREATED, STARTED, COMPLETED
        
        # Stats should show 1 completed, 1 failed
        stats = repo.get_execution_stats(hours=24)
        assert stats["status_counts"].get("completed", 0) == 1
        assert stats["status_counts"].get("failed", 0) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
