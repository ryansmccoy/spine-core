"""Context manager for tracked workflow execution.

Provides a clean interface for running workflows with automatic:
- Execution record creation
- Concurrency locking
- Status updates
- Failure handling with DLQ
- Event recording

Architecture:

    .. code-block:: text

        tracked_execution() lifecycle:

        ┌─────────────────────────────────────────────┐
        │ 1. Check idempotency (skip if done)      │
        │ 2. Create execution in ledger             │
        │ 3. Acquire concurrency lock               │
        │ 4. Mark RUNNING                           │
        │ 5. ─── yield ctx ───  (user code runs)   │
        │ 6a. Mark COMPLETED (on success)           │
        │ 6b. Mark FAILED + DLQ (on exception)      │
        │ 7. Release lock (always)                  │
        └─────────────────────────────────────────────┘

    .. mermaid::

        sequenceDiagram
            participant C as Caller
            participant TE as tracked_execution
            participant L as ExecutionLedger
            participant G as ConcurrencyGuard
            participant D as DLQManager

            C->>TE: with tracked_execution(...)
            TE->>L: create_execution()
            TE->>G: acquire(lock_key)
            G-->>TE: lock acquired
            TE->>L: update_status(RUNNING)
            TE-->>C: yield ctx
            Note over C: User code runs
            alt Success
                C->>TE: exit (no exception)
                TE->>L: update_status(COMPLETED)
            else Failure
                C->>TE: raise Exception
                TE->>L: update_status(FAILED)
                TE->>D: add_to_dlq()
            end
            TE->>G: release(lock_key)

Example:
    >>> from spine.execution.context import TrackedExecution
    >>>
    >>> async with TrackedExecution(
    ...     ledger=ledger,
    ...     guard=guard,
    ...     dlq=dlq,
    ...     workflow="sec.filings",
    ...     params={"date": "2024-01-01"},
    ... ) as ctx:
    ...     result = await fetch_filings(ctx.params)
    ...     ctx.set_result(result)

Manifesto:
    Every execution needs a consistent view of its parameters,
    credentials, and accumulated state.  ExecutionContext is the
    single immutable token passed through the call chain so
    downstream code never depends on ambient globals.

Tags:
    spine-core, execution, context, parameters, immutable-state

Doc-Types:
    api-reference
"""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .concurrency import ConcurrencyGuard
from .dlq import DLQManager
from .ledger import ExecutionLedger
from .models import Execution, ExecutionStatus, TriggerSource


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class ExecutionLockError(Exception):
    """Raised when execution lock cannot be acquired."""

    pass


@dataclass
class ExecutionContext:
    """Context object available during tracked execution.

    Provides access to execution details and methods to update state.

    .. code-block:: text

        ExecutionContext
        ├── .id         → execution UUID
        ├── .workflow   → workflow name
        ├── .params     → execution parameters
        ├── .set_result(data)     → store result for COMPLETED
        ├── .set_metadata(k, v)  → attach metadata
        └── .log_progress(msg)   → emit progress event
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
    def workflow(self) -> str:
        """Get workflow name."""
        return self.execution.workflow

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
            data={"message": message, **data},
        )


@contextmanager
def tracked_execution(
    ledger: ExecutionLedger,
    guard: ConcurrencyGuard | None,
    dlq: DLQManager | None,
    workflow: str,
    params: dict[str, Any] | None = None,
    *,
    trigger_source: TriggerSource = TriggerSource.API,
    idempotency_key: str | None = None,
    lock_timeout: int = 3600,
    skip_if_completed: bool = True,
    add_to_dlq_on_failure: bool = True,
) -> Generator[ExecutionContext, None, None]:
    """Context manager for tracked workflow execution.

    Args:
        ledger: Execution ledger for recording
        guard: Concurrency guard for locking (optional)
        dlq: Dead letter queue for failures (optional)
        workflow: Workflow name
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
    lock_key = f"workflow:{workflow}"
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
        workflow=workflow,
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
                raise ExecutionLockError(f"Could not acquire lock for {workflow}")

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
                workflow=workflow,
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
    workflow: str,
    params: dict[str, Any] | None = None,
    *,
    trigger_source: TriggerSource = TriggerSource.API,
    idempotency_key: str | None = None,
    lock_timeout: int = 3600,
    skip_if_completed: bool = True,
    add_to_dlq_on_failure: bool = True,
) -> AsyncGenerator[ExecutionContext, None]:
    """Async context manager for tracked workflow execution.

    Same as tracked_execution but for async code.
    """
    params = params or {}
    lock_key = f"workflow:{workflow}"
    lock_acquired = False

    # Check idempotency
    if idempotency_key and skip_if_completed:
        existing = ledger.get_by_idempotency_key(idempotency_key)
        if existing and existing.status == ExecutionStatus.COMPLETED:
            yield ExecutionContext(execution=existing, ledger=ledger)
            return

    # Create execution
    execution = Execution.create(
        workflow=workflow,
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
                raise ExecutionLockError(f"Could not acquire lock for {workflow}")

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
                workflow=workflow,
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
