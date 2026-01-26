"""Execution domain models.

Defines the core data structures for the execution system:
- Execution: A pipeline/task execution record
- ExecutionEvent: Event-sourced lifecycle events
- DeadLetter: Failed execution in the dead letter queue

These models are used by ExecutionLedger, DLQManager, and the API layer.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class ExecutionStatus(str, Enum):
    """Status of a pipeline execution."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class EventType(str, Enum):
    """Types of execution events."""

    CREATED = "created"
    QUEUED = "queued"
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRIED = "retried"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


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
    """Represents a pipeline execution.
    
    This is the core record stored in core_executions. It tracks
    the full lifecycle of a pipeline run.
    
    Example:
        >>> execution = Execution.create(
        ...     pipeline="finra.otc.ingest",
        ...     params={"week_ending": "2025-01-09"},
        ...     lane="default",
        ... )
        >>> print(execution.id)  # uuid
        >>> print(execution.status)  # ExecutionStatus.PENDING
    """

    id: str
    pipeline: str
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
        pipeline: str,
        params: dict[str, Any] | None = None,
        lane: str = "default",
        trigger_source: TriggerSource = TriggerSource.API,
        parent_execution_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> "Execution":
        """Create a new execution in PENDING status."""
        return cls(
            id=str(uuid.uuid4()),
            pipeline=pipeline,
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
            "pipeline": self.pipeline,
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
        event_type: EventType,
        data: dict[str, Any] | None = None,
    ) -> "ExecutionEvent":
        """Create a new event."""
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
            "event_type": self.event_type.value,
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
        ...     pipeline="finra.otc.ingest",
        ...     params={"week_ending": "2025-01-09"},
        ...     error="Connection timeout",
        ...     retry_count=3,
        ...     max_retries=3,
        ...     created_at=utcnow(),
        ... )
    """

    id: str
    execution_id: str
    pipeline: str
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
            "pipeline": self.pipeline,
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
    
    Locks prevent overlapping execution of the same pipeline/params.
    """

    lock_key: str
    execution_id: str
    acquired_at: datetime
    expires_at: datetime

    def is_expired(self) -> bool:
        """Check if this lock has expired."""
        return utcnow() > self.expires_at
