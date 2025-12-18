"""Tests for batch execution."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from spine.execution.batch import (
    BatchItem,
    BatchResult,
    BatchBuilder,
    BatchExecutor,
)
from spine.execution.models import ExecutionStatus


class TestBatchItem:
    """Tests for BatchItem dataclass."""

    def test_create_batch_item(self):
        """Test creating a batch item."""
        item = BatchItem(
            id="item-1",
            workflow="test.pipeline",
            params={"date": "2024-01-01"},
        )
        assert item.id == "item-1"
        assert item.workflow == "test.pipeline"
        assert item.params == {"date": "2024-01-01"}
        assert item.execution_id is None
        assert item.status == ExecutionStatus.PENDING

    def test_create_with_all_fields(self):
        """Test creating with all fields."""
        now = datetime.now(timezone.utc)
        item = BatchItem(
            id="item-123",
            workflow="test.pipeline",
            params={"key": "value"},
            execution_id="exec-456",
            status=ExecutionStatus.COMPLETED,
            error=None,
            result={"output": "data"},
            started_at=now,
            completed_at=now,
        )
        assert item.id == "item-123"
        assert item.execution_id == "exec-456"
        assert item.status == ExecutionStatus.COMPLETED
        assert item.result == {"output": "data"}


class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_create_batch_result(self):
        """Test creating a batch result."""
        now = datetime.now(timezone.utc)
        items = [
            BatchItem(id="1", workflow="p1", params={}),
            BatchItem(id="2", workflow="p2", params={}),
        ]
        result = BatchResult(
            batch_id="batch-123",
            items=items,
            started_at=now,
        )
        assert result.batch_id == "batch-123"
        assert result.total == 2
        assert result.completed_at is None

    def test_result_counts(self):
        """Test result counting properties."""
        now = datetime.now(timezone.utc)
        items = [
            BatchItem(id="1", workflow="p1", params={}, status=ExecutionStatus.COMPLETED),
            BatchItem(id="2", workflow="p2", params={}, status=ExecutionStatus.COMPLETED),
            BatchItem(id="3", workflow="p3", params={}, status=ExecutionStatus.FAILED),
            BatchItem(id="4", workflow="p4", params={}, status=ExecutionStatus.PENDING),
        ]
        result = BatchResult(
            batch_id="batch-123",
            items=items,
            started_at=now,
        )
        assert result.total == 4
        assert result.successful == 2
        assert result.failed == 1
        assert result.pending == 1
        assert result.success_rate == 50.0

    def test_result_duration(self):
        """Test result duration calculation."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 12, 0, 10, tzinfo=timezone.utc)
        
        result = BatchResult(
            batch_id="batch-123",
            items=[],
            started_at=start,
            completed_at=end,
        )
        assert result.duration_seconds == 10.0

    def test_result_to_dict(self):
        """Test result serialization."""
        now = datetime.now(timezone.utc)
        items = [
            BatchItem(id="1", workflow="p1", params={"x": 1}, status=ExecutionStatus.COMPLETED),
        ]
        result = BatchResult(
            batch_id="batch-123",
            items=items,
            started_at=now,
            completed_at=now,
        )
        
        data = result.to_dict()
        
        assert data["batch_id"] == "batch-123"
        assert data["total"] == 1
        assert data["successful"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["workflow"] == "p1"


class TestBatchExecutor:
    """Tests for BatchExecutor."""

    def test_add_item(self):
        """Test adding items to batch."""
        ledger = MagicMock()
        executor = BatchExecutor(ledger)
        
        item_id = executor.add("workflow_a", params={"date": "2024-01-01"})
        
        assert item_id is not None
        assert executor.item_count == 1

    def test_add_multiple_items(self):
        """Test adding multiple items."""
        ledger = MagicMock()
        executor = BatchExecutor(ledger)
        
        executor.add("workflow_a", params={"x": 1})
        executor.add("workflow_b", params={"x": 2})
        executor.add("workflow_c", params={"x": 3})
        
        assert executor.item_count == 3

    def test_clear_items(self):
        """Test clearing items."""
        ledger = MagicMock()
        executor = BatchExecutor(ledger)
        
        executor.add("p1")
        executor.add("p2")
        assert executor.item_count == 2
        
        executor.clear()
        assert executor.item_count == 0

    def test_register_handler(self):
        """Test registering a workflow handler."""
        ledger = MagicMock()
        executor = BatchExecutor(ledger)
        
        def my_handler(params):
            return {"result": "ok"}
        
        executor.register_handler("my.workflow", my_handler)
        
        handler = executor._get_handler("my.workflow")
        assert handler is my_handler

    def test_get_default_handler(self):
        """Test getting default handler."""
        ledger = MagicMock()
        default_handler = MagicMock()
        executor = BatchExecutor(ledger, default_handler=default_handler)
        
        handler = executor._get_handler("unknown.workflow")
        assert handler is default_handler

    @patch("spine.execution.batch.tracked_execution")
    def test_run_all_sequential(self, mock_tracked):
        """Test sequential batch execution."""
        ledger = MagicMock()
        executor = BatchExecutor(ledger)
        
        # Mock the tracked_execution context manager
        mock_ctx = MagicMock()
        mock_ctx.id = "exec-123"
        mock_tracked.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_tracked.return_value.__exit__ = MagicMock(return_value=False)
        
        executor.add("p1", {"x": 1})
        executor.add("p2", {"x": 2})
        
        result = executor.run_all(parallel=False)
        
        assert result.total == 2
        assert result.batch_id is not None
        assert result.completed_at is not None

    @patch("spine.execution.batch.tracked_execution")
    def test_run_all_with_progress(self, mock_tracked):
        """Test batch execution with progress callback."""
        ledger = MagicMock()
        executor = BatchExecutor(ledger)
        
        mock_ctx = MagicMock()
        mock_ctx.id = "exec-123"
        mock_tracked.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_tracked.return_value.__exit__ = MagicMock(return_value=False)
        
        progress_items = []
        def on_progress(item):
            progress_items.append(item.id)
        
        executor.add("p1")
        executor.add("p2")
        
        executor.run_all(parallel=False, on_progress=on_progress)
        
        assert len(progress_items) == 2

    @patch("spine.execution.batch.tracked_execution")
    def test_run_sequential_stop_on_failure(self, mock_tracked):
        """Test sequential run with stop on failure."""
        ledger = MagicMock()
        executor = BatchExecutor(ledger)
        
        call_count = 0
        
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("Simulated failure")
            mock_ctx = MagicMock()
            mock_ctx.id = f"exec-{call_count}"
            return mock_ctx
        
        mock_tracked.return_value.__enter__ = side_effect
        mock_tracked.return_value.__exit__ = MagicMock(return_value=False)
        
        executor.add("p1")
        executor.add("p2")
        executor.add("p3")
        
        result = executor.run_sequential(stop_on_failure=True)
        
        # Should stop after the failure
        assert result.failed >= 1


class TestBatchBuilder:
    """Tests for BatchBuilder fluent API."""

    def test_add_single_item(self):
        """Test adding a single item."""
        ledger = MagicMock()
        builder = BatchBuilder(ledger)
        
        builder.add("workflow_a", params={"date": "2024-01-01"})
        
        assert builder._executor.item_count == 1

    def test_add_multiple_items(self):
        """Test adding multiple items."""
        ledger = MagicMock()
        builder = BatchBuilder(ledger)
        
        builder.add("workflow_a", params={"x": 1})
        builder.add("workflow_b", params={"x": 2})
        builder.add("workflow_c", params={"x": 3})
        
        assert builder._executor.item_count == 3

    def test_fluent_api(self):
        """Test fluent API chaining."""
        ledger = MagicMock()
        
        builder = (
            BatchBuilder(ledger)
            .add("p1", params={"x": 1})
            .add("p2", params={"x": 2})
            .add("p3", params={"x": 3})
        )
        
        assert builder._executor.item_count == 3

    def test_parallel_config(self):
        """Test parallel configuration."""
        ledger = MagicMock()
        
        builder = BatchBuilder(ledger).parallel(max_workers=8)
        
        assert builder._parallel is True
        assert builder._max_parallel == 8

    def test_sequential_config(self):
        """Test sequential configuration."""
        ledger = MagicMock()
        
        builder = BatchBuilder(ledger).sequential(stop_on_failure=True)
        
        assert builder._parallel is False
        assert builder._stop_on_failure is True

    def test_handler_registration(self):
        """Test handler registration via builder."""
        ledger = MagicMock()
        
        def my_handler(params):
            return {"result": "ok"}
        
        builder = BatchBuilder(ledger).handler("my.workflow", my_handler)
        
        assert builder._executor._get_handler("my.workflow") is my_handler

    def test_on_progress_config(self):
        """Test progress callback configuration."""
        ledger = MagicMock()
        
        def my_callback(item):
            pass
        
        builder = BatchBuilder(ledger).on_progress(my_callback)
        
        assert builder._on_progress is my_callback

    @patch("spine.execution.batch.tracked_execution")
    def test_run(self, mock_tracked):
        """Test running the batch."""
        ledger = MagicMock()
        
        mock_ctx = MagicMock()
        mock_ctx.id = "exec-123"
        mock_tracked.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_tracked.return_value.__exit__ = MagicMock(return_value=False)
        
        result = (
            BatchBuilder(ledger)
            .add("p1")
            .add("p2")
            .sequential()
            .run()
        )
        
        assert result.total == 2
        assert result.batch_id is not None
