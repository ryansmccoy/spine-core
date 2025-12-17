"""Event system for cross-app communication.

Why This Package Exists
-----------------------
Pipeline modules (ops, scheduling, execution) need to notify each other
when things happen -- run completed, quality check failed, schedule fired.
Without a shared event bus, modules either import each other directly
(creating circular dependencies) or silently lose events.

The ``EventBus`` protocol with pluggable backends (in-memory, Redis)
decouples producers from consumers.  In-memory works for single-process
deployments; Redis Pub/Sub enables multi-node event delivery.

Usage::

    from spine.core.events import Event, get_event_bus

    bus = get_event_bus()

    # Publish
    event = Event(
        event_type="run.completed",
        source="pipeline-runner",
        payload={"run_id": "abc-123", "status": "success"},
    )
    await bus.publish(event)

    # Subscribe (supports wildcards: "run.*")
    async def handler(event: Event):
        print(f"Run {event.payload['run_id']} completed!")
    sub_id = await bus.subscribe("run.*", handler)

Modules
-------
memory      InMemoryEventBus -- asyncio queues, single-node
redis       RedisEventBus -- Redis Pub/Sub, multi-node
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "Event",
    "EventBus",
    "EventHandler",
    "get_event_bus",
    "set_event_bus",
    "publish_event",
]


# ── Event Model ──────────────────────────────────────────────────────────


@dataclass
class Event:
    """Immutable event payload for cross-app communication.

    Attributes:
        event_type: Dot-separated type (e.g., ``run.started``, ``workflow.failed``)
        source: Origin system/component
        payload: Event-specific data
        timestamp: When the event occurred (UTC)
        correlation_id: Optional ID linking related events
        event_id: Unique event identifier
    """

    event_type: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def matches(self, pattern: str) -> bool:
        """Check if event type matches a pattern (supports wildcards).

        Examples:
            - ``run.*`` matches ``run.started``, ``run.completed``
            - ``*`` matches everything
            - ``run.started`` matches exactly ``run.started``
        """
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return self.event_type.startswith(prefix + ".")
        return self.event_type == pattern


# ── Type Aliases ─────────────────────────────────────────────────────────

EventHandler = Callable[[Event], Awaitable[None]]


# ── EventBus Protocol ────────────────────────────────────────────────────


@runtime_checkable
class EventBus(Protocol):
    """Protocol for event bus implementations.

    Supports publish/subscribe with wildcard patterns. Implementations
    must be async-compatible.
    """

    async def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers.

        Args:
            event: The event to publish
        """
        ...

    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> str:
        """Subscribe to events matching a pattern.

        Args:
            event_type: Pattern to match (e.g., ``run.*``, ``workflow.completed``)
            handler: Async callback for matching events

        Returns:
            Subscription ID for later unsubscription
        """
        ...

    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription.

        Args:
            subscription_id: ID returned from :meth:`subscribe`
        """
        ...

    async def close(self) -> None:
        """Clean up resources (connections, queues, etc.)."""
        ...


# ── Default Event Bus Singleton ──────────────────────────────────────────

_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance.

    Returns the configured event bus, creating an in-memory one if
    none has been set.

    Returns:
        The EventBus instance
    """
    global _event_bus
    if _event_bus is None:
        from spine.core.events.memory import InMemoryEventBus
        _event_bus = InMemoryEventBus()
    return _event_bus


def set_event_bus(bus: EventBus) -> None:
    """Set the global event bus instance.

    Args:
        bus: EventBus implementation to use globally
    """
    global _event_bus
    _event_bus = bus


def publish_event(
    event_type: str,
    source: str,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> None:
    """Publish an event to the global event bus (fire-and-forget).

    This is a sync-safe helper for publishing events from synchronous code.
    It schedules the async publish call without blocking. If there's no
    running event loop, the event is published in a new loop.

    Args:
        event_type: Dot-separated event type (e.g., "run.submitted")
        source: Component origin (e.g., "ops.runs")
        payload: Event-specific data dictionary
        correlation_id: Optional correlation ID for linking related events

    Example::

        from spine.core.events import publish_event

        # In an ops function:
        publish_event(
            "run.submitted",
            "ops.runs",
            {"run_id": "abc-123", "pipeline": "daily_etl"},
        )
    """
    import asyncio

    event = Event(
        event_type=event_type,
        source=source,
        payload=payload or {},
        correlation_id=correlation_id,
    )
    bus = get_event_bus()

    try:
        loop = asyncio.get_running_loop()
        # Schedule publish without blocking
        loop.create_task(bus.publish(event))
    except RuntimeError:
        # No running loop — run in a new one (sync context)
        try:
            asyncio.run(bus.publish(event))
        except Exception:
            # Swallow errors — event publishing is fire-and-forget
            pass
