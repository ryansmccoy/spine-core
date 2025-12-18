"""Execution domain models.

Defines the core data structures for the execution system:
- Execution: A pipeline/task execution record
- ExecutionEvent: Event-sourced lifecycle events
- DeadLetter: Failed execution in the dead letter queue

These models are used by ExecutionLedger, DLQManager, and the API layer.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class InvalidTransitionError(ValueError):
    """Raised when an illegal state transition is attempted.

    State machines enforce which transitions are valid.  This error fires
    when code tries to move from a state that doesn't allow the target
    (e.g. COMPLETED → RUNNING).

    Architecture Decision:
        Transition validation is deliberately strict.  If you discover a
        legitimate transition that is blocked, add it to VALID_TRANSITIONS
        explicitly — never remove the guard.
    """

    def __init__(self, current: str, target: str, enum_name: str = "Status") -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid {enum_name} transition: {current} → {target}"
        )


class ExecutionStatus(str, Enum):
    """Status of a pipeline execution.

    State transitions are enforced via ``VALID_TRANSITIONS``.  Use
    ``validate_transition()`` or the ``transition_to()`` helper before
    changing status on any :class:`Execution` instance.

    Valid transition graph::

        PENDING  → QUEUED | RUNNING | CANCELLED
        QUEUED   → RUNNING | CANCELLED
        RUNNING  → COMPLETED | FAILED | CANCELLED | TIMED_OUT
        FAILED   → PENDING (retry)
        TIMED_OUT → PENDING (retry)
        COMPLETED → (terminal)
        CANCELLED → (terminal)
    """

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


# --- ExecutionStatus transition rules ---

EXECUTION_VALID_TRANSITIONS: dict[ExecutionStatus, frozenset[ExecutionStatus]] = {
    ExecutionStatus.PENDING: frozenset({
        ExecutionStatus.QUEUED,
        ExecutionStatus.RUNNING,
        ExecutionStatus.CANCELLED,
    }),
    ExecutionStatus.QUEUED: frozenset({
        ExecutionStatus.RUNNING,
        ExecutionStatus.CANCELLED,
    }),
    ExecutionStatus.RUNNING: frozenset({
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
        ExecutionStatus.TIMED_OUT,
    }),
    ExecutionStatus.FAILED: frozenset({
        ExecutionStatus.PENDING,  # retry
    }),
    ExecutionStatus.TIMED_OUT: frozenset({
        ExecutionStatus.PENDING,  # retry
    }),
    ExecutionStatus.COMPLETED: frozenset(),  # terminal
    ExecutionStatus.CANCELLED: frozenset(),  # terminal
}


def validate_execution_transition(
    current: ExecutionStatus,
    target: ExecutionStatus,
) -> None:
    """Raise :class:`InvalidTransitionError` if *current → target* is illegal.

    Args:
        current: The current execution status.
        target: The desired next status.

    Raises:
        InvalidTransitionError: If the transition is not in
            ``EXECUTION_VALID_TRANSITIONS``.

    Example:
        >>> validate_execution_transition(ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED)
        >>> # OK — no exception
        >>> validate_execution_transition(ExecutionStatus.COMPLETED, ExecutionStatus.RUNNING)
        InvalidTransitionError: Invalid ExecutionStatus transition: completed → running
    """
    allowed = EXECUTION_VALID_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(current.value, target.value, "ExecutionStatus")


class EventType(str, Enum):
    """Canonical event types for execution lifecycle.

    This is the preferred EventType — use this for new code.
    The plain-class ``spine.execution.events.EventType`` is deprecated.
    """

    # Core lifecycle
    CREATED = "created"
    QUEUED = "queued"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

    # Progress
    PROGRESS = "progress"
    HEARTBEAT = "heartbeat"

    # Retry lifecycle
    RETRY_SCHEDULED = "retry_scheduled"
    RETRIED = "retried"

    # DLQ
    DEAD_LETTERED = "dead_lettered"
    REPROCESSED = "reprocessed"

    # Workflow-specific
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_SKIPPED = "step_skipped"

    # External
    WEBHOOK_SENT = "webhook_sent"
    ALERT_TRIGGERED = "alert_triggered"

    # Job Engine (container lifecycle)
    IMAGE_PULLING = "image_pulling"
    IMAGE_PULLED = "image_pulled"
    CONTAINER_CREATING = "container_creating"
    CONTAINER_CREATED = "container_created"
    ARTIFACT_READY = "artifact_ready"
    COST_RECORDED = "cost_recorded"
    CLEANUP_STARTED = "cleanup_started"
    CLEANUP_COMPLETED = "cleanup_completed"

    # Job Engine (reconciler)
    RECONCILED = "reconciled"
    ORPHAN_DETECTED = "orphan_detected"


class TriggerSource(str, Enum):
    """Source that triggered the execution."""

    API = "api"
    CLI = "cli"
    SCHEDULE = "schedule"
    RETRY = "retry"
    WORKFLOW = "workflow"  # Child of a workflow step
    INTERNAL = "internal"


@dataclass
class Execution:
    """Represents a workflow execution.

    This is the core record stored in core_executions. It tracks
    the full lifecycle of a workflow run.

    Example:
        >>> execution = Execution.create(
        ...     workflow="finra.otc.ingest",
        ...     params={"week_ending": "2025-01-09"},
        ...     lane="default",
        ... )
        >>> print(execution.id)  # uuid
        >>> print(execution.status)  # ExecutionStatus.PENDING
    """

    id: str
    workflow: str
    params: dict[str, Any]
    status: ExecutionStatus
    lane: str
    trigger_source: TriggerSource
    parent_execution_id: str | None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0
    idempotency_key: str | None = None

    @classmethod
    def create(
        cls,
        workflow: str,
        params: dict[str, Any] | None = None,
        lane: str = "default",
        trigger_source: TriggerSource = TriggerSource.API,
        parent_execution_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> "Execution":
        """Create a new execution in PENDING status."""
        return cls(
            id=str(uuid.uuid4()),
            workflow=workflow,
            params=params or {},
            status=ExecutionStatus.PENDING,
            lane=lane,
            trigger_source=trigger_source,
            parent_execution_id=parent_execution_id,
            created_at=utcnow(),
            idempotency_key=idempotency_key,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "workflow": self.workflow,
            "params": self.params,
            "status": self.status.value,
            "lane": self.lane,
            "trigger_source": self.trigger_source.value,
            "parent_execution_id": self.parent_execution_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "idempotency_key": self.idempotency_key,
        }


@dataclass
class ExecutionEvent:
    """Event in the execution lifecycle.

    Events are immutable, append-only records that track what happened
    to an execution. They enable debugging, observability, and replay.

    Example:
        >>> event = ExecutionEvent.create(
        ...     execution_id="exec-123",
        ...     event_type=EventType.STARTED,
        ...     data={"worker": "worker-1"},
        ... )
    """

    id: str
    execution_id: str
    event_type: EventType
    timestamp: datetime
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        execution_id: str,
        event_type: "EventType | str",
        data: dict[str, Any] | None = None,
    ) -> "ExecutionEvent":
        """Create a new event.

        Args:
            execution_id: The execution UUID
            event_type: EventType enum or string constant (e.g. "started")
            data: Optional event data
        """
        # Coerce string to EventType enum for consistency
        if isinstance(event_type, str) and not isinstance(event_type, EventType):
            event_type = EventType(event_type)
        return cls(
            id=str(uuid.uuid4()),
            execution_id=execution_id,
            event_type=event_type,
            timestamp=utcnow(),
            data=data or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "event_type": self.event_type.value if hasattr(self.event_type, "value") else str(self.event_type),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "data": self.data,
        }


@dataclass
class DeadLetter:
    """A failed execution in the dead letter queue.

    Dead letters capture failed executions for manual inspection and retry.
    They persist until explicitly resolved.

    Example:
        >>> dlq_entry = DeadLetter(
        ...     id="dlq-123",
        ...     execution_id="exec-456",
        ...     workflow="finra.otc.ingest",
        ...     params={"week_ending": "2025-01-09"},
        ...     error="Connection timeout",
        ...     retry_count=3,
        ...     max_retries=3,
        ...     created_at=utcnow(),
        ... )
    """

    id: str
    execution_id: str
    workflow: str
    params: dict[str, Any]
    error: str
    retry_count: int
    max_retries: int
    created_at: datetime
    last_retry_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None

    def can_retry(self) -> bool:
        """Check if this dead letter can be retried."""
        return self.resolved_at is None and self.retry_count < self.max_retries

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "workflow": self.workflow,
            "params": self.params,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_retry_at": self.last_retry_at.isoformat() if self.last_retry_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
        }


@dataclass
class ConcurrencyLock:
    """A concurrency lock record.

    Locks prevent overlapping execution of the same workflow/params.
    """

    lock_key: str
    execution_id: str
    acquired_at: datetime
    expires_at: datetime

    def is_expired(self) -> bool:
        """Check if this lock has expired."""
        return utcnow() > self.expires_at
