"""Run Events — immutable event-sourced execution history.

WHY
───
Mutable status fields only show *current* state.  Events capture the
complete lifecycle (“who changed what, when, why”) enabling
debugging, observability dashboards, and deterministic replay.

ARCHITECTURE
────────────
::

    RunEvent
      ├── run_id      ─ which run
      ├── event_type  ─ submitted / started / completed / failed / ...
      ├── timestamp   ─ when
      └── data        ─ arbitrary payload (params, error, metrics)

    Events are append-only; never update or delete.

Related modules:
    runs.py       — RunRecord (mutable current state)
    dispatcher.py — emits events on submission/completion
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


# EventType has been consolidated into spine.execution.models.EventType (str Enum).
# Import from there for all new code:
#     from spine.execution.models import EventType
