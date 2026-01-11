"""Domain models."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
import uuid


class ExecutionStatus(str, Enum):
    """Status of a pipeline execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    """Types of execution events."""

    CREATED = "created"
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRIED = "retried"
    CANCELLED = "cancelled"


class TriggerSource(str, Enum):
    """Source that triggered the execution."""

    API = "api"
    CLI = "cli"
    SCHEDULE = "schedule"
    RETRY = "retry"
    INTERNAL = "internal"


@dataclass
class Execution:
    """Represents a pipeline execution."""

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

    @classmethod
    def create(
        cls,
        pipeline: str,
        params: dict[str, Any] | None = None,
        lane: str = "default",
        trigger_source: TriggerSource = TriggerSource.API,
        parent_execution_id: str | None = None,
    ) -> "Execution":
        """Create a new execution."""
        return cls(
            id=str(uuid.uuid4()),
            pipeline=pipeline,
            params=params or {},
            status=ExecutionStatus.PENDING,
            lane=lane,
            trigger_source=trigger_source,
            parent_execution_id=parent_execution_id,
            created_at=datetime.utcnow(),
        )


@dataclass
class ExecutionEvent:
    """Event in the execution lifecycle."""

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
            timestamp=datetime.utcnow(),
            data=data or {},
        )


@dataclass
class DeadLetter:
    """A failed execution in the dead letter queue."""

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


# Domain-specific models are in domains/<domain>/models.py
