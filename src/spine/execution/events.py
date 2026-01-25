"""Run events - event-sourced execution history.

This module defines RunEvent and standard event types for tracking the
lifecycle of work executions. Events are immutable, append-only records
that enable debugging, observability, and replay.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RunEvent:
    """Event-sourced history for observability and debugging.
    
    Events are immutable append-only records that track the lifecycle
    of a run. This enables:
    - Debugging: trace what happened and when
    - Observability: monitor run patterns
    - Replay: reconstruct run state from events
    
    Example:
        >>> event = RunEvent(
        ...     event_id="evt-001",
        ...     run_id="run-abc",
        ...     event_type=EventType.CREATED,
        ...     timestamp=datetime.utcnow(),
        ...     data={"spec": spec.to_dict()},
        ... )
    """
    
    event_id: str
    """Unique event identifier (UUID)"""
    
    run_id: str
    """Which run this event belongs to"""
    
    event_type: str
    """Event type (created, queued, started, completed, etc.)"""
    
    timestamp: datetime
    """When this event occurred"""
    
    data: dict[str, Any] = field(default_factory=dict)
    """Event-specific payload"""
    
    source: str = "dispatcher"
    """Where this event originated (dispatcher, executor, worker, etc.)"""
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON/storage."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "data": self.data,
            "source": self.source,
        }


class EventType:
    """Standard event types for run lifecycle.
    
    Use these constants for consistency across the codebase:
        >>> await dispatcher._record_event(run_id, EventType.CREATED)
    """
    
    # Core lifecycle
    CREATED = "created"              # Run record created
    QUEUED = "queued"                # Submitted to executor
    STARTED = "started"              # Execution began
    COMPLETED = "completed"          # Finished successfully
    FAILED = "failed"                # Finished with error
    CANCELLED = "cancelled"          # Cancelled by user/system
    
    # Progress updates
    PROGRESS = "progress"            # Progress update (percentage, message)
    HEARTBEAT = "heartbeat"          # Worker heartbeat (still alive)
    
    # Retry lifecycle
    RETRY_SCHEDULED = "retry_scheduled"  # Retry scheduled after failure
    RETRIED = "retried"              # New run created as retry
    
    # DLQ
    DEAD_LETTERED = "dead_lettered"  # Moved to DLQ after retries
    REPROCESSED = "reprocessed"      # Moved from DLQ back to queue
    
    # Workflow-specific
    STEP_STARTED = "step_started"    # Workflow step began
    STEP_COMPLETED = "step_completed"  # Workflow step completed
    STEP_FAILED = "step_failed"      # Workflow step failed
    STEP_SKIPPED = "step_skipped"    # Workflow step skipped (choice branch)
    
    # External
    WEBHOOK_SENT = "webhook_sent"    # Notification sent
    ALERT_TRIGGERED = "alert_triggered"  # Alert fired
