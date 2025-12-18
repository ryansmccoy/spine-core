"""Unit tests for spine.execution.ledger module.

Tests ExecutionLedger CRUD operations in isolation.
"""

import sqlite3
import pytest

from spine.core.schema import CORE_DDL
from spine.execution.models import (
    Execution,
    ExecutionStatus,
    EventType,
    TriggerSource,
)
from spine.execution.ledger import ExecutionLedger


@pytest.fixture
def conn():
    """Create in-memory SQLite database with execution tables."""
    conn = sqlite3.connect(":memory:")
    for name, ddl in CORE_DDL.items():
        conn.execute(ddl)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def ledger(conn):
    """Create ExecutionLedger instance."""
    return ExecutionLedger(conn)


class TestCreateExecution:
    """Test execution creation."""

    def test_create_stores_all_fields(self, ledger, conn):
        """All execution fields are persisted."""
        execution = Execution.create(
            workflow="test.pipeline",
            params={"key": "value"},
            lane="priority",
            trigger_source=TriggerSource.CLI,
        )
        
        ledger.create_execution(execution)
        
        # Verify in database
        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("SELECT * FROM core_executions WHERE id = ?", (execution.id,))
        row = cursor.fetchone()
        
        assert row is not None
        assert row["workflow"] == "test.pipeline"
        assert "key" in row["params"]  # params (JSON)
        assert row["status"] == "pending"

    def test_create_records_created_event(self, ledger, conn):
        """Creating execution records a CREATED event."""
        execution = Execution.create(workflow="test.pipeline")
        ledger.create_execution(execution)
        
        cursor = conn.cursor()
        cursor.execute(
            "SELECT event_type FROM core_execution_events WHERE execution_id = ?",
            (execution.id,),
        )
        events = [row[0] for row in cursor.fetchall()]
        
        assert "created" in events


class TestGetExecution:
    """Test execution retrieval."""

    def test_get_existing(self, ledger):
        """Get returns existing execution."""
        execution = Execution.create(workflow="test.pipeline")
        ledger.create_execution(execution)
        
        retrieved = ledger.get_execution(execution.id)
        
        assert retrieved is not None
        assert retrieved.id == execution.id
        assert retrieved.workflow == execution.workflow

    def test_get_nonexistent(self, ledger):
        """Get returns None for nonexistent execution."""
        retrieved = ledger.get_execution("nonexistent-id")
        assert retrieved is None


class TestUpdateStatus:
    """Test status updates."""

    def test_update_to_running_sets_started_at(self, ledger):
        """Updating to RUNNING sets started_at timestamp."""
        execution = Execution.create(workflow="test.pipeline")
        ledger.create_execution(execution)
        
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        
        updated = ledger.get_execution(execution.id)
        assert updated.status == ExecutionStatus.RUNNING
        assert updated.started_at is not None

    def test_update_to_completed_sets_completed_at(self, ledger):
        """Updating to COMPLETED sets completed_at timestamp."""
        execution = Execution.create(workflow="test.pipeline")
        ledger.create_execution(execution)
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        
        ledger.update_status(
            execution.id,
            ExecutionStatus.COMPLETED,
            result={"rows": 100},
        )
        
        updated = ledger.get_execution(execution.id)
        assert updated.status == ExecutionStatus.COMPLETED
        assert updated.completed_at is not None
        assert updated.result["rows"] == 100

    def test_update_to_failed_sets_error(self, ledger):
        """Updating to FAILED sets error message."""
        execution = Execution.create(workflow="test.pipeline")
        ledger.create_execution(execution)
        
        ledger.update_status(
            execution.id,
            ExecutionStatus.FAILED,
            error="Connection timeout",
        )
        
        updated = ledger.get_execution(execution.id)
        assert updated.status == ExecutionStatus.FAILED
        assert "timeout" in updated.error.lower()


class TestIdempotencyKey:
    """Test idempotency key lookups."""

    def test_find_by_idempotency_key(self, ledger):
        """Can find execution by idempotency key."""
        execution = Execution.create(
            workflow="test.pipeline",
            idempotency_key="unique-key-123",
        )
        ledger.create_execution(execution)
        
        found = ledger.get_by_idempotency_key("unique-key-123")
        
        assert found is not None
        assert found.id == execution.id

    def test_idempotency_key_not_found(self, ledger):
        """Returns None for nonexistent idempotency key."""
        found = ledger.get_by_idempotency_key("does-not-exist")
        assert found is None


class TestListExecutions:
    """Test listing executions."""

    def test_list_with_limit(self, ledger):
        """Limit parameter controls result count."""
        for i in range(10):
            ledger.create_execution(Execution.create(workflow="test.pipeline"))
        
        results = ledger.list_executions(limit=5)
        assert len(results) == 5

    def test_list_filter_by_workflow(self, ledger):
        """Filter by workflow name."""
        ledger.create_execution(Execution.create(workflow="workflow.a"))
        ledger.create_execution(Execution.create(workflow="workflow.a"))
        ledger.create_execution(Execution.create(workflow="workflow.b"))
        
        results = ledger.list_executions(workflow="workflow.a")
        
        assert len(results) == 2
        assert all(r.workflow == "workflow.a" for r in results)

    def test_list_filter_by_status(self, ledger):
        """Filter by status."""
        exec1 = Execution.create(workflow="test")
        ledger.create_execution(exec1)
        ledger.update_status(exec1.id, ExecutionStatus.COMPLETED)
        
        exec2 = Execution.create(workflow="test")
        ledger.create_execution(exec2)
        
        completed = ledger.list_executions(status=ExecutionStatus.COMPLETED)
        pending = ledger.list_executions(status=ExecutionStatus.PENDING)
        
        assert len(completed) == 1
        assert len(pending) == 1

    def test_list_ordered_by_created_at_desc(self, ledger):
        """Results are ordered by created_at descending."""
        ids = []
        for i in range(5):
            execution = Execution.create(workflow="test")
            ledger.create_execution(execution)
            ids.append(execution.id)
        
        results = ledger.list_executions()
        result_ids = [r.id for r in results]
        
        # Most recent first
        assert result_ids == list(reversed(ids))


class TestEvents:
    """Test event recording and retrieval."""

    def test_record_custom_event(self, ledger):
        """Can record custom events."""
        execution = Execution.create(workflow="test")
        ledger.create_execution(execution)
        
        event = ledger.record_event(
            execution.id,
            EventType.PROGRESS,
            data={"percent": 50},
        )
        
        assert event.id is not None
        assert event.event_type == EventType.PROGRESS
        assert event.data["percent"] == 50

    def test_get_events_ordered_chronologically(self, ledger):
        """Events are returned in chronological order."""
        execution = Execution.create(workflow="test")
        ledger.create_execution(execution)
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        ledger.update_status(execution.id, ExecutionStatus.COMPLETED)
        
        events = ledger.get_events(execution.id)
        
        # Should be: CREATED, STARTED, COMPLETED
        assert len(events) >= 3
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)


class TestIncrementRetry:
    """Test retry count incrementing."""

    def test_increment_returns_new_count(self, ledger):
        """Increment returns the new retry count."""
        execution = Execution.create(workflow="test")
        ledger.create_execution(execution)
        
        count1 = ledger.increment_retry(execution.id)
        count2 = ledger.increment_retry(execution.id)
        
        assert count1 == 1
        assert count2 == 2

    def test_increment_records_retried_event(self, ledger):
        """Incrementing retry records a RETRIED event."""
        execution = Execution.create(workflow="test")
        ledger.create_execution(execution)
        ledger.increment_retry(execution.id)
        
        events = ledger.get_events(execution.id)
        event_types = [e.event_type for e in events]
        
        assert EventType.RETRIED in event_types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
