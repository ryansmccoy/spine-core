"""Tests for TrackedExecution context manager."""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from spine.execution.context import (
    ExecutionContext,
    ExecutionLockError,
    tracked_execution,
    tracked_execution_async,
)
from spine.execution.models import Execution, ExecutionStatus, TriggerSource


class MockLedger:
    """Mock ExecutionLedger for testing."""

    def __init__(self):
        self.executions = {}
        self.status_updates = []
        self._idempotency_map = {}

    def create_execution(self, execution: Execution):
        self.executions[execution.id] = execution
        if execution.idempotency_key:
            self._idempotency_map[execution.idempotency_key] = execution

    def update_status(self, execution_id: str, status: ExecutionStatus, **kwargs):
        self.status_updates.append({
            "execution_id": execution_id,
            "status": status,
            **kwargs,
        })
        if execution_id in self.executions:
            self.executions[execution_id].status = status

    def get_by_idempotency_key(self, key: str) -> Execution | None:
        return self._idempotency_map.get(key)

    def record_event(self, execution_id: str, **kwargs):
        pass


class MockConcurrencyGuard:
    """Mock ConcurrencyGuard for testing."""

    def __init__(self, allow_lock=True):
        self.allow_lock = allow_lock
        self.acquire_calls = []
        self.release_calls = []

    def acquire(self, lock_key: str, execution_id: str, timeout_seconds: int = 3600) -> bool:
        self.acquire_calls.append({
            "lock_key": lock_key,
            "execution_id": execution_id,
            "timeout_seconds": timeout_seconds,
        })
        return self.allow_lock

    def release(self, lock_key: str, execution_id: str):
        self.release_calls.append({
            "lock_key": lock_key,
            "execution_id": execution_id,
        })
        return True


class MockDLQManager:
    """Mock DLQManager for testing."""

    def __init__(self):
        self.add_calls = []

    def add_to_dlq(self, execution_id: str, workflow: str, params: dict, error: str, **kwargs):
        self.add_calls.append({
            "execution_id": execution_id,
            "workflow": workflow,
            "params": params,
            "error": error,
            **kwargs,
        })


class TestExecutionContext:
    """Tests for ExecutionContext dataclass."""

    def test_create_with_execution(self):
        """Test creating context with execution object."""
        execution = Execution.create(
            workflow="test.pipeline",
            params={"key": "value"},
        )
        ledger = MockLedger()
        
        ctx = ExecutionContext(execution=execution, ledger=ledger)
        
        assert ctx.id == execution.id
        assert ctx.workflow == "test.pipeline"
        assert ctx.params == {"key": "value"}

    def test_set_result(self):
        """Test setting result."""
        execution = Execution.create(workflow="test", params={})
        ledger = MockLedger()
        
        ctx = ExecutionContext(execution=execution, ledger=ledger)
        ctx.set_result({"output": "data"})
        
        assert ctx._result == {"output": "data"}

    def test_set_metadata(self):
        """Test setting metadata."""
        execution = Execution.create(workflow="test", params={})
        ledger = MockLedger()
        
        ctx = ExecutionContext(execution=execution, ledger=ledger)
        ctx.set_metadata("key1", "value1")
        ctx.set_metadata("key2", "value2")
        
        assert ctx._metadata == {"key1": "value1", "key2": "value2"}


class TestTrackedExecution:
    """Tests for tracked_execution context manager."""

    def test_successful_execution(self):
        """Test successful execution flow."""
        ledger = MockLedger()
        guard = MockConcurrencyGuard()
        dlq = MockDLQManager()

        with tracked_execution(
            ledger=ledger,
            guard=guard,
            dlq=dlq,
            workflow="test.pipeline",
            params={"date": "2024-01-01"},
        ) as ctx:
            assert ctx.id is not None
            assert ctx.workflow == "test.pipeline"
            assert ctx.params == {"date": "2024-01-01"}
        
        # Verify execution was created
        assert len(ledger.executions) == 1
        
        # Verify status updates: RUNNING then COMPLETED
        statuses = [u["status"] for u in ledger.status_updates]
        assert ExecutionStatus.RUNNING in statuses
        assert ExecutionStatus.COMPLETED in statuses
        
        # No DLQ since success
        assert len(dlq.add_calls) == 0

    def test_failed_execution_sends_to_dlq(self):
        """Test failed execution sends to DLQ."""
        ledger = MockLedger()
        guard = MockConcurrencyGuard()
        dlq = MockDLQManager()

        with pytest.raises(ValueError):
            with tracked_execution(
                ledger=ledger,
                guard=guard,
                dlq=dlq,
                workflow="test.pipeline",
            ) as ctx:
                raise ValueError("Test error")
        
        # Verify status was FAILED
        statuses = [u["status"] for u in ledger.status_updates]
        assert ExecutionStatus.FAILED in statuses
        
        # Verify DLQ received the failure
        assert len(dlq.add_calls) == 1
        assert "Test error" in dlq.add_calls[0]["error"]

    def test_lock_acquired_and_released(self):
        """Test lock is acquired and released."""
        ledger = MockLedger()
        guard = MockConcurrencyGuard()
        dlq = MockDLQManager()

        with tracked_execution(
            ledger=ledger,
            guard=guard,
            dlq=dlq,
            workflow="test.pipeline",
        ) as ctx:
            pass
        
        # Verify lock was acquired
        assert len(guard.acquire_calls) == 1
        assert "workflow:test.pipeline" in guard.acquire_calls[0]["lock_key"]
        
        # Verify lock was released
        assert len(guard.release_calls) == 1

    def test_lock_released_on_failure(self):
        """Test lock is released even on failure."""
        ledger = MockLedger()
        guard = MockConcurrencyGuard()
        dlq = MockDLQManager()

        with pytest.raises(ValueError):
            with tracked_execution(
                ledger=ledger,
                guard=guard,
                dlq=dlq,
                workflow="test.pipeline",
            ) as ctx:
                raise ValueError("Error")
        
        # Lock should still be released
        assert len(guard.release_calls) == 1

    def test_raises_lock_error_when_lock_unavailable(self):
        """Test execution raises error when lock unavailable."""
        ledger = MockLedger()
        guard = MockConcurrencyGuard(allow_lock=False)
        dlq = MockDLQManager()

        with pytest.raises(ExecutionLockError):
            with tracked_execution(
                ledger=ledger,
                guard=guard,
                dlq=dlq,
                workflow="test.pipeline",
            ) as ctx:
                pass
        
        # Verify execution was marked as cancelled
        statuses = [u["status"] for u in ledger.status_updates]
        assert ExecutionStatus.CANCELLED in statuses

    def test_without_concurrency_guard(self):
        """Test execution without concurrency guard."""
        ledger = MockLedger()
        dlq = MockDLQManager()

        with tracked_execution(
            ledger=ledger,
            guard=None,
            dlq=dlq,
            workflow="test.pipeline",
        ) as ctx:
            assert ctx.id is not None
        
        # Should complete without lock
        statuses = [u["status"] for u in ledger.status_updates]
        assert ExecutionStatus.COMPLETED in statuses

    def test_without_dlq_manager(self):
        """Test execution without DLQ manager."""
        ledger = MockLedger()

        with pytest.raises(ValueError):
            with tracked_execution(
                ledger=ledger,
                guard=None,
                dlq=None,
                workflow="test.pipeline",
            ) as ctx:
                raise ValueError("No DLQ")
        
        # Verify failure was recorded
        statuses = [u["status"] for u in ledger.status_updates]
        assert ExecutionStatus.FAILED in statuses

    def test_params_passed_to_context(self):
        """Test params are available in context."""
        ledger = MockLedger()

        with tracked_execution(
            ledger=ledger,
            guard=None,
            dlq=None,
            workflow="test.pipeline",
            params={"date": "2024-01-01", "ticker": "AAPL"},
        ) as ctx:
            assert ctx.params == {"date": "2024-01-01", "ticker": "AAPL"}

    def test_set_result_persisted(self):
        """Test result is set via context."""
        ledger = MockLedger()

        with tracked_execution(
            ledger=ledger,
            guard=None,
            dlq=None,
            workflow="test.pipeline",
        ) as ctx:
            ctx.set_result({"output": "data"})
        
        # Verify result was passed to status update
        completed_update = [u for u in ledger.status_updates if u["status"] == ExecutionStatus.COMPLETED][0]
        assert completed_update.get("result") == {"output": "data"}

    def test_idempotency_skips_completed(self):
        """Test idempotency skips already completed execution."""
        ledger = MockLedger()
        
        # Create an already-completed execution
        existing = Execution.create(
            workflow="test.pipeline",
            params={},
            idempotency_key="my-key",
        )
        existing.status = ExecutionStatus.COMPLETED
        ledger._idempotency_map["my-key"] = existing

        executed = False
        with tracked_execution(
            ledger=ledger,
            guard=None,
            dlq=None,
            workflow="test.pipeline",
            idempotency_key="my-key",
            skip_if_completed=True,
        ) as ctx:
            # This should use the existing execution, not create new
            executed = True
            assert ctx.id == existing.id
        
        assert executed
        # No new execution should be created
        assert len(ledger.executions) == 0


class TestTrackedExecutionAsync:
    """Tests for async tracked execution."""

    @pytest.mark.asyncio
    async def test_async_successful_execution(self):
        """Test async successful execution."""
        ledger = MockLedger()
        guard = MockConcurrencyGuard()
        dlq = MockDLQManager()

        async with tracked_execution_async(
            ledger=ledger,
            guard=guard,
            dlq=dlq,
            workflow="test.async_pipeline",
        ) as ctx:
            assert ctx.id is not None
            await asyncio.sleep(0.01)  # Simulate async work
        
        # Verify completion
        statuses = [u["status"] for u in ledger.status_updates]
        assert ExecutionStatus.COMPLETED in statuses

    @pytest.mark.asyncio
    async def test_async_failed_execution(self):
        """Test async failed execution sends to DLQ."""
        ledger = MockLedger()
        dlq = MockDLQManager()

        with pytest.raises(RuntimeError):
            async with tracked_execution_async(
                ledger=ledger,
                guard=None,
                dlq=dlq,
                workflow="test.async_pipeline",
            ) as ctx:
                raise RuntimeError("Async error")
        
        # Verify DLQ received failure
        assert len(dlq.add_calls) == 1

    @pytest.mark.asyncio
    async def test_async_with_params(self):
        """Test async execution with params."""
        ledger = MockLedger()

        async with tracked_execution_async(
            ledger=ledger,
            guard=None,
            dlq=None,
            workflow="test.pipeline",
            params={"async_param": True},
        ) as ctx:
            assert ctx.params == {"async_param": True}

    @pytest.mark.asyncio
    async def test_async_lock_released_on_failure(self):
        """Test async lock is released on failure."""
        ledger = MockLedger()
        guard = MockConcurrencyGuard()
        dlq = MockDLQManager()

        with pytest.raises(ValueError):
            async with tracked_execution_async(
                ledger=ledger,
                guard=guard,
                dlq=dlq,
                workflow="test.pipeline",
            ) as ctx:
                raise ValueError("Error")
        
        # Lock should be released
        assert len(guard.release_calls) == 1
