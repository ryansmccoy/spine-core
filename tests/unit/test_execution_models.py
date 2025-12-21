"""Unit tests for spine.execution.models module.

Tests the dataclasses and enums:
- ExecutionStatus, EventType, TriggerSource enums
- Execution, ExecutionEvent, DeadLetter, ConcurrencyLock dataclasses
"""

import pytest
from datetime import datetime, timezone, timedelta

from spine.execution.models import (
    ExecutionStatus,
    EventType,
    TriggerSource,
    Execution,
    ExecutionEvent,
    DeadLetter,
    ConcurrencyLock,
    utcnow,
)


class TestEnums:
    """Test enum values and string representations."""

    def test_execution_status_values(self):
        """All expected status values exist."""
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.QUEUED.value == "queued"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.CANCELLED.value == "cancelled"
        assert ExecutionStatus.TIMED_OUT.value == "timed_out"

    def test_event_type_values(self):
        """All expected event types exist."""
        assert EventType.CREATED.value == "created"
        assert EventType.QUEUED.value == "queued"
        assert EventType.STARTED.value == "started"
        assert EventType.PROGRESS.value == "progress"
        assert EventType.COMPLETED.value == "completed"
        assert EventType.FAILED.value == "failed"
        assert EventType.RETRIED.value == "retried"
        assert EventType.CANCELLED.value == "cancelled"

    def test_trigger_source_values(self):
        """All expected trigger sources exist."""
        assert TriggerSource.API.value == "api"
        assert TriggerSource.CLI.value == "cli"
        assert TriggerSource.SCHEDULE.value == "schedule"
        assert TriggerSource.RETRY.value == "retry"
        assert TriggerSource.WORKFLOW.value == "workflow"
        assert TriggerSource.INTERNAL.value == "internal"


class TestExecution:
    """Test Execution dataclass."""

    def test_create_defaults(self):
        """Create execution with minimal args uses defaults."""
        execution = Execution.create(workflow="test.operation")
        
        assert execution.id is not None
        assert len(execution.id) == 36  # UUID format
        assert execution.workflow == "test.operation"
        assert execution.params == {}
        assert execution.status == ExecutionStatus.PENDING
        assert execution.lane == "default"
        assert execution.trigger_source == TriggerSource.API
        assert execution.parent_execution_id is None
        assert execution.created_at is not None
        assert execution.retry_count == 0

    def test_create_with_all_params(self):
        """Create execution with all parameters."""
        execution = Execution.create(
            workflow="finra.otc.ingest",
            params={"week_ending": "2025-01-09", "tier": "NMS_TIER_1"},
            lane="priority",
            trigger_source=TriggerSource.SCHEDULE,
            parent_execution_id="parent-123",
            idempotency_key="finra:2025-01-09",
        )
        
        assert execution.workflow == "finra.otc.ingest"
        assert execution.params["week_ending"] == "2025-01-09"
        assert execution.lane == "priority"
        assert execution.trigger_source == TriggerSource.SCHEDULE
        assert execution.parent_execution_id == "parent-123"
        assert execution.idempotency_key == "finra:2025-01-09"

    def test_to_dict(self):
        """Execution serializes to dictionary."""
        execution = Execution.create(
            workflow="test.operation",
            params={"key": "value"},
        )
        
        d = execution.to_dict()
        
        assert d["id"] == execution.id
        assert d["workflow"] == "test.operation"
        assert d["params"] == {"key": "value"}
        assert d["status"] == "pending"
        assert d["lane"] == "default"
        assert d["trigger_source"] == "api"
        assert "created_at" in d

    def test_unique_ids(self):
        """Each execution gets a unique ID."""
        ids = set()
        for _ in range(100):
            execution = Execution.create(workflow="test")
            ids.add(execution.id)
        
        assert len(ids) == 100


class TestExecutionEvent:
    """Test ExecutionEvent dataclass."""

    def test_create_event(self):
        """Create event with defaults."""
        event = ExecutionEvent.create(
            execution_id="exec-123",
            event_type=EventType.STARTED,
        )
        
        assert event.id is not None
        assert event.execution_id == "exec-123"
        assert event.event_type == EventType.STARTED
        assert event.timestamp is not None
        assert event.data == {}

    def test_create_event_with_data(self):
        """Create event with custom data."""
        event = ExecutionEvent.create(
            execution_id="exec-123",
            event_type=EventType.PROGRESS,
            data={"rows_processed": 5000, "percent": 50},
        )
        
        assert event.data["rows_processed"] == 5000
        assert event.data["percent"] == 50

    def test_to_dict(self):
        """Event serializes to dictionary."""
        event = ExecutionEvent.create(
            execution_id="exec-123",
            event_type=EventType.COMPLETED,
            data={"result": "success"},
        )
        
        d = event.to_dict()
        
        assert d["execution_id"] == "exec-123"
        assert d["event_type"] == "completed"
        assert d["data"]["result"] == "success"


class TestDeadLetter:
    """Test DeadLetter dataclass."""

    def test_can_retry_under_limit(self):
        """Can retry when retry_count < max_retries."""
        dlq = DeadLetter(
            id="dlq-123",
            execution_id="exec-123",
            workflow="test.operation",
            params={},
            error="Connection error",
            retry_count=2,
            max_retries=3,
            created_at=utcnow(),
        )
        
        assert dlq.can_retry() is True

    def test_cannot_retry_at_limit(self):
        """Cannot retry when retry_count >= max_retries."""
        dlq = DeadLetter(
            id="dlq-123",
            execution_id="exec-123",
            workflow="test.operation",
            params={},
            error="Connection error",
            retry_count=3,
            max_retries=3,
            created_at=utcnow(),
        )
        
        assert dlq.can_retry() is False

    def test_cannot_retry_when_resolved(self):
        """Cannot retry when already resolved."""
        dlq = DeadLetter(
            id="dlq-123",
            execution_id="exec-123",
            workflow="test.operation",
            params={},
            error="Connection error",
            retry_count=0,
            max_retries=3,
            created_at=utcnow(),
            resolved_at=utcnow(),
        )
        
        assert dlq.can_retry() is False

    def test_to_dict(self):
        """DeadLetter serializes to dictionary."""
        dlq = DeadLetter(
            id="dlq-123",
            execution_id="exec-456",
            workflow="test.operation",
            params={"key": "value"},
            error="Error message",
            retry_count=1,
            max_retries=3,
            created_at=utcnow(),
        )
        
        d = dlq.to_dict()
        
        assert d["id"] == "dlq-123"
        assert d["execution_id"] == "exec-456"
        assert d["error"] == "Error message"
        assert d["retry_count"] == 1


class TestConcurrencyLock:
    """Test ConcurrencyLock dataclass."""

    def test_is_expired_past(self):
        """Lock is expired when expires_at is in the past."""
        lock = ConcurrencyLock(
            lock_key="test.lock",
            execution_id="exec-123",
            acquired_at=utcnow() - timedelta(hours=2),
            expires_at=utcnow() - timedelta(hours=1),
        )
        
        assert lock.is_expired() is True

    def test_is_not_expired_future(self):
        """Lock is not expired when expires_at is in the future."""
        lock = ConcurrencyLock(
            lock_key="test.lock",
            execution_id="exec-123",
            acquired_at=utcnow(),
            expires_at=utcnow() + timedelta(hours=1),
        )
        
        assert lock.is_expired() is False


class TestUtcnow:
    """Test the utcnow helper function."""

    def test_returns_timezone_aware(self):
        """utcnow() returns timezone-aware datetime."""
        now = utcnow()
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc

    def test_is_recent(self):
        """utcnow() returns current time."""
        before = datetime.now(timezone.utc)
        now = utcnow()
        after = datetime.now(timezone.utc)
        
        assert before <= now <= after


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
