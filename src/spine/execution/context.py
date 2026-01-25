"""Context manager for tracked pipeline execution.

Provides a clean interface for running pipelines with automatic:
- Execution record creation
- Concurrency locking
- Status updates
- Failure handling with DLQ
- Event recording

Example:
    >>> from spine.execution.context import TrackedExecution
    >>>
    >>> async with TrackedExecution(
    ...     ledger=ledger,
    ...     guard=guard,
    ...     dlq=dlq,
    ...     pipeline="sec.filings",
    ...     params={"date": "2024-01-01"},
    ... ) as ctx:
    ...     result = await fetch_filings(ctx.params)
    ...     ctx.set_result(result)
"""

import traceback
from contextlib import contextmanager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generator, AsyncGenerator

from .models import Execution, ExecutionStatus, TriggerSource
from .ledger import ExecutionLedger
from .concurrency import ConcurrencyGuard
from .dlq import DLQManager


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class ExecutionLockError(Exception):
    """Raised when execution lock cannot be acquired."""
    pass


@dataclass
class ExecutionContext:
    """Context object available during tracked execution.
    
    Provides access to execution details and methods to update state.
    """

    execution: Execution
    ledger: ExecutionLedger
    _result: dict[str, Any] | None = field(default=None, init=False)
    _metadata: dict[str, Any] = field(default_factory=dict, init=False)

    @property
    def id(self) -> str:
        """Get execution ID."""
        return self.execution.id

    @property
    def pipeline(self) -> str:
        """Get pipeline name."""
        return self.execution.pipeline

    @property
    def params(self) -> dict[str, Any]:
        """Get execution parameters."""
        return self.execution.params

    def set_result(self, result: dict[str, Any]) -> None:
        """Set execution result."""
        self._result = result

    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata value."""
        self._metadata[key] = value

    def log_progress(self, message: str, **data: Any) -> None:
        """Log a progress event."""
        self.ledger.record_event(
            self.execution.id,
            event_type="progress",
            message=message,
            metadata=data,
        )


@contextmanager
def tracked_execution(
    ledger: ExecutionLedger,
    guard: ConcurrencyGuard | None,
    dlq: DLQManager | None,
    pipeline: str,
    params: dict[str, Any] | None = None,
    *,
    trigger_source: TriggerSource = TriggerSource.API,
    idempotency_key: str | None = None,
    lock_timeout: int = 3600,
    skip_if_completed: bool = True,
    add_to_dlq_on_failure: bool = True,
) -> Generator[ExecutionContext, None, None]:
    """Context manager for tracked pipeline execution.
    
    Args:
        ledger: Execution ledger for recording
        guard: Concurrency guard for locking (optional)
        dlq: Dead letter queue for failures (optional)
        pipeline: Pipeline name
        params: Execution parameters
        trigger_source: What triggered this execution
        idempotency_key: Key for idempotent execution
        lock_timeout: Lock timeout in seconds
        skip_if_completed: Skip if idempotency key already completed
        add_to_dlq_on_failure: Add to DLQ on failure
        
    Yields:
        ExecutionContext for the running execution
        
    Raises:
        ExecutionLockError: If lock cannot be acquired
    """
    params = params or {}
    lock_key = f"pipeline:{pipeline}"
    lock_acquired = False
    
    # Check idempotency
    if idempotency_key and skip_if_completed:
        existing = ledger.get_by_idempotency_key(idempotency_key)
        if existing and existing.status == ExecutionStatus.COMPLETED:
            # Return a "fake" context that does nothing
            yield ExecutionContext(execution=existing, ledger=ledger)
            return
    
    # Create execution
    execution = Execution.create(
        pipeline=pipeline,
        params=params,
        trigger_source=trigger_source,
        idempotency_key=idempotency_key,
    )
    ledger.create_execution(execution)
    
    ctx = ExecutionContext(execution=execution, ledger=ledger)
    
    try:
        # Acquire lock if guard provided
        if guard is not None:
            lock_acquired = guard.acquire(
                lock_key=lock_key,
                execution_id=execution.id,
                timeout_seconds=lock_timeout,
            )
            if not lock_acquired:
                ledger.update_status(execution.id, ExecutionStatus.CANCELLED)
                raise ExecutionLockError(
                    f"Could not acquire lock for {pipeline}"
                )
        
        # Mark as running
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        
        # Yield control to user code
        yield ctx
        
        # Mark as completed
        ledger.update_status(
            execution.id,
            ExecutionStatus.COMPLETED,
            result=ctx._result,
        )
        
    except ExecutionLockError:
        raise  # Re-raise lock errors
        
    except Exception as e:
        # Mark as failed
        error_msg = str(e)
        ledger.update_status(
            execution.id,
            ExecutionStatus.FAILED,
            error=error_msg,
        )
        
        # Add to DLQ if enabled
        if add_to_dlq_on_failure and dlq is not None:
            dlq.add_to_dlq(
                execution_id=execution.id,
                pipeline=pipeline,
                params=params,
                error=error_msg,
            )
        
        raise
        
    finally:
        # Always release lock
        if lock_acquired and guard is not None:
            guard.release(lock_key, execution_id=execution.id)


@asynccontextmanager
async def tracked_execution_async(
    ledger: ExecutionLedger,
    guard: ConcurrencyGuard | None,
    dlq: DLQManager | None,
    pipeline: str,
    params: dict[str, Any] | None = None,
    *,
    trigger_source: TriggerSource = TriggerSource.API,
    idempotency_key: str | None = None,
    lock_timeout: int = 3600,
    skip_if_completed: bool = True,
    add_to_dlq_on_failure: bool = True,
) -> AsyncGenerator[ExecutionContext, None]:
    """Async context manager for tracked pipeline execution.
    
    Same as tracked_execution but for async code.
    """
    params = params or {}
    lock_key = f"pipeline:{pipeline}"
    lock_acquired = False
    
    # Check idempotency
    if idempotency_key and skip_if_completed:
        existing = ledger.get_by_idempotency_key(idempotency_key)
        if existing and existing.status == ExecutionStatus.COMPLETED:
            yield ExecutionContext(execution=existing, ledger=ledger)
            return
    
    # Create execution
    execution = Execution.create(
        pipeline=pipeline,
        params=params,
        trigger_source=trigger_source,
        idempotency_key=idempotency_key,
    )
    ledger.create_execution(execution)
    
    ctx = ExecutionContext(execution=execution, ledger=ledger)
    
    try:
        # Acquire lock if guard provided
        if guard is not None:
            lock_acquired = guard.acquire(
                lock_key=lock_key,
                execution_id=execution.id,
                timeout_seconds=lock_timeout,
            )
            if not lock_acquired:
                ledger.update_status(execution.id, ExecutionStatus.CANCELLED)
                raise ExecutionLockError(
                    f"Could not acquire lock for {pipeline}"
                )
        
        # Mark as running
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        
        # Yield control to user code
        yield ctx
        
        # Mark as completed
        ledger.update_status(
            execution.id,
            ExecutionStatus.COMPLETED,
            result=ctx._result,
        )
        
    except ExecutionLockError:
        raise
        
    except Exception as e:
        error_msg = str(e)
        ledger.update_status(
            execution.id,
            ExecutionStatus.FAILED,
            error=error_msg,
        )
        
        if add_to_dlq_on_failure and dlq is not None:
            dlq.add_to_dlq(
                execution_id=execution.id,
                pipeline=pipeline,
                params=params,
                error=error_msg,
            )
        
        raise
        
    finally:
        if lock_acquired and guard is not None:
            guard.release(lock_key, execution_id=execution.id)


# Convenience aliases
TrackedExecution = tracked_execution
TrackedExecutionAsync = tracked_execution_async
