"""Batch execution for running multiple pipelines.

Provides coordinated execution of multiple pipelines with:
- Parallel or sequential execution
- Progress tracking
- Aggregate results

Example:
    >>> from spine.execution.batch import BatchExecutor
    >>>
    >>> batch = BatchExecutor(ledger, guard, dlq, max_parallel=4)
    >>> batch.add("sec.filings", {"date": "2024-01-01"})
    >>> batch.add("sec.filings", {"date": "2024-01-02"})
    >>> batch.add("market.prices", {"symbol": "AAPL"})
    >>>
    >>> results = batch.run_all()
    >>> print(f"Completed: {results.successful}/{results.total}")
"""

import concurrent.futures
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
import uuid

from .models import Execution, ExecutionStatus, TriggerSource
from .ledger import ExecutionLedger
from .concurrency import ConcurrencyGuard
from .dlq import DLQManager
from .context import tracked_execution


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass
class BatchItem:
    """A single item in a batch."""

    id: str
    pipeline: str
    params: dict[str, Any]
    execution_id: str | None = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    error: str | None = None
    result: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class BatchResult:
    """Result of a batch execution."""

    batch_id: str
    items: list[BatchItem]
    started_at: datetime
    completed_at: datetime | None = None

    @property
    def total(self) -> int:
        """Total number of items."""
        return len(self.items)

    @property
    def successful(self) -> int:
        """Number of successful items."""
        return sum(1 for item in self.items if item.status == ExecutionStatus.COMPLETED)

    @property
    def failed(self) -> int:
        """Number of failed items."""
        return sum(1 for item in self.items if item.status == ExecutionStatus.FAILED)

    @property
    def pending(self) -> int:
        """Number of pending items."""
        return sum(1 for item in self.items if item.status == ExecutionStatus.PENDING)

    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        if self.total == 0:
            return 0.0
        return (self.successful / self.total) * 100

    @property
    def duration_seconds(self) -> float | None:
        """Total duration in seconds."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "batch_id": self.batch_id,
            "total": self.total,
            "successful": self.successful,
            "failed": self.failed,
            "pending": self.pending,
            "success_rate": self.success_rate,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "items": [
                {
                    "id": item.id,
                    "pipeline": item.pipeline,
                    "params": item.params,
                    "execution_id": item.execution_id,
                    "status": item.status.value,
                    "error": item.error,
                }
                for item in self.items
            ],
        }


class BatchExecutor:
    """Execute multiple pipelines as a coordinated batch.
    
    Supports:
    - Adding items to batch
    - Parallel or sequential execution
    - Custom pipeline handlers
    - Progress callbacks
    """

    def __init__(
        self,
        ledger: ExecutionLedger,
        guard: ConcurrencyGuard | None = None,
        dlq: DLQManager | None = None,
        max_parallel: int = 4,
        default_handler: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ):
        """Initialize batch executor.
        
        Args:
            ledger: Execution ledger for tracking
            guard: Concurrency guard for locking
            dlq: Dead letter queue for failures
            max_parallel: Maximum parallel executions
            default_handler: Default function to execute pipelines
        """
        self._ledger = ledger
        self._guard = guard
        self._dlq = dlq
        self._max_parallel = max_parallel
        self._default_handler = default_handler
        
        self._items: list[BatchItem] = []
        self._handlers: dict[str, Callable] = {}
        self._lock = threading.Lock()

    def add(
        self,
        pipeline: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Add a pipeline execution to the batch.
        
        Args:
            pipeline: Pipeline name
            params: Execution parameters
            
        Returns:
            Item ID for tracking
        """
        item_id = str(uuid.uuid4())
        item = BatchItem(
            id=item_id,
            pipeline=pipeline,
            params=params or {},
        )
        
        with self._lock:
            self._items.append(item)
        
        return item_id

    def register_handler(
        self,
        pipeline: str,
        handler: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Register a handler for a specific pipeline.
        
        Args:
            pipeline: Pipeline name
            handler: Function that takes params and returns result
        """
        self._handlers[pipeline] = handler

    def _get_handler(self, pipeline: str) -> Callable | None:
        """Get handler for a pipeline."""
        if pipeline in self._handlers:
            return self._handlers[pipeline]
        return self._default_handler

    def _execute_item(
        self,
        item: BatchItem,
        on_progress: Callable[[BatchItem], None] | None = None,
    ) -> None:
        """Execute a single batch item."""
        item.started_at = utcnow()
        handler = self._get_handler(item.pipeline)
        
        try:
            with tracked_execution(
                ledger=self._ledger,
                guard=self._guard,
                dlq=self._dlq,
                pipeline=item.pipeline,
                params=item.params,
                add_to_dlq_on_failure=True,
            ) as ctx:
                item.execution_id = ctx.id
                
                if handler is not None:
                    result = handler(item.params)
                    ctx.set_result(result)
                    item.result = result
                
                item.status = ExecutionStatus.COMPLETED
                
        except Exception as e:
            item.status = ExecutionStatus.FAILED
            item.error = str(e)
        
        finally:
            item.completed_at = utcnow()
            if on_progress:
                on_progress(item)

    def run_all(
        self,
        parallel: bool = True,
        on_progress: Callable[[BatchItem], None] | None = None,
    ) -> BatchResult:
        """Run all items in the batch.
        
        Args:
            parallel: Run in parallel (True) or sequential (False)
            on_progress: Callback for each completed item
            
        Returns:
            BatchResult with all execution results
        """
        batch_id = str(uuid.uuid4())
        started_at = utcnow()
        
        with self._lock:
            items = list(self._items)
        
        if parallel and self._max_parallel > 1:
            # Parallel execution
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self._max_parallel
            ) as executor:
                futures = [
                    executor.submit(self._execute_item, item, on_progress)
                    for item in items
                ]
                concurrent.futures.wait(futures)
        else:
            # Sequential execution
            for item in items:
                self._execute_item(item, on_progress)
        
        return BatchResult(
            batch_id=batch_id,
            items=items,
            started_at=started_at,
            completed_at=utcnow(),
        )

    def run_sequential(
        self,
        on_progress: Callable[[BatchItem], None] | None = None,
        stop_on_failure: bool = False,
    ) -> BatchResult:
        """Run items sequentially with optional early stop.
        
        Args:
            on_progress: Callback for each completed item
            stop_on_failure: Stop batch on first failure
            
        Returns:
            BatchResult with execution results
        """
        batch_id = str(uuid.uuid4())
        started_at = utcnow()
        
        with self._lock:
            items = list(self._items)
        
        for item in items:
            self._execute_item(item, on_progress)
            
            if stop_on_failure and item.status == ExecutionStatus.FAILED:
                break
        
        return BatchResult(
            batch_id=batch_id,
            items=items,
            started_at=started_at,
            completed_at=utcnow(),
        )

    def clear(self) -> None:
        """Clear all items from the batch."""
        with self._lock:
            self._items.clear()

    @property
    def item_count(self) -> int:
        """Get number of items in batch."""
        with self._lock:
            return len(self._items)


class BatchBuilder:
    """Fluent builder for batch executions.
    
    Example:
        >>> result = (
        ...     BatchBuilder(ledger, guard, dlq)
        ...     .add("pipeline.a", {"x": 1})
        ...     .add("pipeline.a", {"x": 2})
        ...     .add("pipeline.b", {"y": 3})
        ...     .parallel(max_workers=4)
        ...     .run()
        ... )
    """

    def __init__(
        self,
        ledger: ExecutionLedger,
        guard: ConcurrencyGuard | None = None,
        dlq: DLQManager | None = None,
    ):
        self._executor = BatchExecutor(ledger, guard, dlq)
        self._parallel = True
        self._max_parallel = 4
        self._stop_on_failure = False
        self._on_progress: Callable[[BatchItem], None] | None = None

    def add(self, pipeline: str, params: dict[str, Any] | None = None) -> "BatchBuilder":
        """Add a pipeline to the batch."""
        self._executor.add(pipeline, params)
        return self

    def handler(
        self,
        pipeline: str,
        handler: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> "BatchBuilder":
        """Register a handler for a pipeline."""
        self._executor.register_handler(pipeline, handler)
        return self

    def parallel(self, max_workers: int = 4) -> "BatchBuilder":
        """Enable parallel execution."""
        self._parallel = True
        self._max_parallel = max_workers
        self._executor._max_parallel = max_workers
        return self

    def sequential(self, stop_on_failure: bool = False) -> "BatchBuilder":
        """Enable sequential execution."""
        self._parallel = False
        self._stop_on_failure = stop_on_failure
        return self

    def on_progress(
        self,
        callback: Callable[[BatchItem], None],
    ) -> "BatchBuilder":
        """Set progress callback."""
        self._on_progress = callback
        return self

    def run(self) -> BatchResult:
        """Execute the batch."""
        if self._parallel:
            return self._executor.run_all(
                parallel=True,
                on_progress=self._on_progress,
            )
        else:
            return self._executor.run_sequential(
                on_progress=self._on_progress,
                stop_on_failure=self._stop_on_failure,
            )
