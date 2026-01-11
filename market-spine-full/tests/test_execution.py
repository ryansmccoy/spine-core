"""Tests for execution system."""

import pytest
from market_spine.core.models import ExecutionStatus, TriggerSource, EventType


class TestExecutionLedger:
    """Tests for execution ledger."""

    def test_create_and_get_execution(self, db_pool, clean_db, ledger):
        """Test creating and retrieving execution."""
        from market_spine.core.models import Execution

        execution = Execution.create(
            pipeline="test_pipeline",
            params={"key": "value"},
        )

        ledger.create_execution(execution)

        retrieved = ledger.get_execution(execution.id)
        assert retrieved is not None
        assert retrieved.pipeline == "test_pipeline"
        assert retrieved.params == {"key": "value"}
        assert retrieved.status == ExecutionStatus.PENDING

    def test_update_status(self, db_pool, clean_db, ledger):
        """Test updating execution status."""
        from market_spine.core.models import Execution

        execution = Execution.create(pipeline="test")
        ledger.create_execution(execution)

        # Update to running
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        retrieved = ledger.get_execution(execution.id)
        assert retrieved.status == ExecutionStatus.RUNNING
        assert retrieved.started_at is not None

        # Update to completed
        ledger.update_status(
            execution.id,
            ExecutionStatus.COMPLETED,
            result={"count": 10},
        )
        retrieved = ledger.get_execution(execution.id)
        assert retrieved.status == ExecutionStatus.COMPLETED
        assert retrieved.result == {"count": 10}

    def test_execution_events_recorded(self, db_pool, clean_db, ledger):
        """Test that events are recorded for status changes."""
        from market_spine.core.models import Execution

        execution = Execution.create(pipeline="test")
        ledger.create_execution(execution)
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        ledger.update_status(execution.id, ExecutionStatus.COMPLETED)

        events = ledger.get_events(execution.id)
        assert len(events) == 3
        assert events[0].event_type == EventType.CREATED
        assert events[1].event_type == EventType.STARTED
        assert events[2].event_type == EventType.COMPLETED


class TestDispatcher:
    """Tests for dispatcher."""

    def test_submit_creates_execution(self, db_pool, clean_db, dispatcher, ledger):
        """Test that submit creates an execution."""
        execution = dispatcher.submit(
            pipeline="test_ingest",
            params={"source": "synthetic"},
            trigger_source=TriggerSource.API,
        )

        assert execution.id is not None
        assert execution.pipeline == "test_ingest"
        assert execution.status == ExecutionStatus.PENDING

        # Verify in ledger
        retrieved = ledger.get_execution(execution.id)
        assert retrieved is not None

    def test_submit_with_different_trigger_sources(self, db_pool, clean_db, dispatcher):
        """Test submitting with different trigger sources."""
        for source in [TriggerSource.API, TriggerSource.CLI, TriggerSource.SCHEDULE]:
            execution = dispatcher.submit(
                pipeline="test_ingest",
                trigger_source=source,
            )
            assert execution.trigger_source == source


class TestDLQManager:
    """Tests for DLQ manager."""

    def test_add_to_dlq(self, db_pool, clean_db, dlq_manager):
        """Test adding failed execution to DLQ."""
        entry = dlq_manager.add_to_dlq(
            execution_id="exec-123",
            pipeline="test_pipeline",
            params={"key": "value"},
            error="Something failed",
        )

        assert entry.id is not None
        assert entry.execution_id == "exec-123"
        assert entry.error == "Something failed"
        assert entry.retry_count == 0

    def test_can_retry(self, db_pool, clean_db, dlq_manager):
        """Test retry eligibility check."""
        entry = dlq_manager.add_to_dlq(
            execution_id="exec-123",
            pipeline="test",
            params={},
            error="Failed",
        )

        assert dlq_manager.can_retry(entry.id) is True

        # Mark as retrying multiple times
        dlq_manager.mark_retrying(entry.id)
        dlq_manager.mark_retrying(entry.id)
        dlq_manager.mark_retrying(entry.id)

        # Should not be retryable after max retries
        assert dlq_manager.can_retry(entry.id) is False

    def test_resolve(self, db_pool, clean_db, dlq_manager):
        """Test resolving a dead letter."""
        entry = dlq_manager.add_to_dlq(
            execution_id="exec-123",
            pipeline="test",
            params={},
            error="Failed",
        )

        dlq_manager.resolve(entry.id, resolved_by="manual")

        retrieved = dlq_manager.get_dead_letter(entry.id)
        assert retrieved.resolved_at is not None
        assert retrieved.resolved_by == "manual"
        assert dlq_manager.can_retry(entry.id) is False
