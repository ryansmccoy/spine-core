"""Scheduler backend protocol.

┌──────────────────────────────────────────────────────────────────────────────┐
│  SCHEDULER BACKEND PROTOCOL                                                   │
│                                                                               │
│  Design Philosophy:                                                           │
│  This protocol defines the minimal contract for scheduler timing backends.   │
│  The scheduler operates as "beat-as-poller" — backends control WHEN ticks    │
│  happen, while SchedulerService controls WHAT happens on each tick.          │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │           Backend Abstraction Diagram                               │     │
│  │                                                                     │     │
│  │   ┌─────────────────┐       tick()       ┌─────────────────┐       │     │
│  │   │  Thread Backend │ ─────────────────► │  Scheduler      │       │     │
│  │   │  (default)      │                    │  Service        │       │     │
│  │   └─────────────────┘                    │                 │       │     │
│  │                                          │  - Check due    │       │     │
│  │   ┌─────────────────┐       tick()       │  - Acquire lock │       │     │
│  │   │  APScheduler    │ ─────────────────► │  - Dispatch     │       │     │
│  │   │  Backend        │                    │  - Update next  │       │     │
│  │   └─────────────────┘                    └─────────────────┘       │     │
│  │                                                                     │     │
│  │   ┌─────────────────┐       tick()                                 │     │
│  │   │  Celery Beat    │ ─────────────────►                           │     │
│  │   │  Backend        │                                               │     │
│  │   └─────────────────┘                                               │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                               │
│  Responsibility Split:                                                        │
│  - Backend: Controls timing (thread sleep, APScheduler job, Celery task)    │
│  - Service: Controls logic (schedule evaluation, lock, dispatch)             │
│                                                                               │
│  This is the SAME pattern used by market-spine/orchestrator/backends/.       │
└──────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass


TickCallback = Callable[[], Awaitable[None]]


@runtime_checkable
class SchedulerBackend(Protocol):
    """Protocol for pluggable scheduler timing backends.

    A backend is responsible ONLY for timing — calling the tick callback
    at the specified interval. All schedule evaluation logic lives in
    SchedulerService.

    Implementations:
        - ThreadSchedulerBackend: Zero-dependency threading-based (default)
        - APSchedulerBackend: APScheduler-based (requires [scheduler] extra)
        - CeleryBeatBackend: Celery Beat-based (requires [celery] extra)

    Example (custom backend):
        >>> class MyBackend:
        ...     name = "custom"
        ...
        ...     def start(self, tick_callback, interval=10.0):
        ...         self._callback = tick_callback
        ...         my_scheduler.add_job(lambda: asyncio.run(tick_callback()), interval)
        ...
        ...     def stop(self):
        ...         my_scheduler.stop()
        ...
        ...     def health(self) -> dict:
        ...         return {"healthy": True, "backend": "custom"}
    """

    name: str

    def start(
        self,
        tick_callback: TickCallback,
        interval_seconds: float = 10.0,
    ) -> None:
        """Start the scheduler loop.

        Args:
            tick_callback: Async function to call on each tick.
                          The callback handles schedule evaluation.
            interval_seconds: How often to tick (default: 10s).
        """
        ...

    def stop(self) -> None:
        """Stop the scheduler loop gracefully.

        Should wait for current tick to complete before returning.
        """
        ...

    def health(self) -> dict[str, Any]:
        """Return backend health status.

        Returns:
            dict with at least:
                - healthy: bool — whether backend is running
                - backend: str — backend name
                - tick_count: int — number of ticks executed
                - last_tick: str | None — ISO timestamp of last tick
        """
        ...


@dataclass
class BackendHealth:
    """Structured backend health response."""

    healthy: bool
    backend: str
    tick_count: int = 0
    last_tick: datetime | None = None
    drift_ms: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "healthy": self.healthy,
            "backend": self.backend,
            "tick_count": self.tick_count,
            "last_tick": self.last_tick.isoformat() if self.last_tick else None,
            "drift_ms": self.drift_ms,
            **self.extra,
        }
