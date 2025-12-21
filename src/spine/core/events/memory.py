"""
In-memory event bus implementation.

Manifesto:
    Single-process deployments and test suites need a zero-dependency event
    bus that delivers events immediately without external infrastructure.

Uses asyncio queues for single-node deployments. Events are processed
immediately and not persisted.

Tags:
    spine-core, events, in-memory, asyncio, testing, single-node

Doc-Types:
    api-reference
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from spine.core.events import Event, EventHandler

__all__ = ["InMemoryEventBus"]


@dataclass
class Subscription:
    """Internal subscription record."""

    id: str
    pattern: str
    handler: EventHandler


class InMemoryEventBus:
    """In-process event bus for single-node deployments.

    Events are delivered synchronously to all matching handlers.
    Suitable for testing and single-process applications.

    Example::

        bus = InMemoryEventBus()

        async def log_event(event: Event):
            print(f"Event: {event.event_type}")

        await bus.subscribe("*", log_event)
        await bus.publish(Event(event_type="test", source="example"))
        # Output: Event: test
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, Subscription] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers.

        Handlers are called concurrently using asyncio.gather.
        Exceptions in handlers are logged but don't stop delivery.
        """
        if self._closed:
            return

        async with self._lock:
            handlers_to_call: list[tuple[str, EventHandler]] = []
            for sub in self._subscriptions.values():
                if event.matches(sub.pattern):
                    handlers_to_call.append((sub.id, sub.handler))

        if not handlers_to_call:
            return

        # Call handlers concurrently, catching exceptions
        async def safe_call(sub_id: str, handler: EventHandler) -> None:
            try:
                await handler(event)
            except Exception as e:
                from spine.core.logging import get_logger
                log = get_logger("spine.events")
                log.warning(
                    "event_handler_error",
                    subscription_id=sub_id,
                    event_type=event.event_type,
                    error=str(e),
                )

        await asyncio.gather(
            *[safe_call(sub_id, handler) for sub_id, handler in handlers_to_call],
            return_exceptions=True,
        )

    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> str:
        """Subscribe to events matching a pattern.

        Args:
            event_type: Pattern to match (supports ``*`` and ``type.*``)
            handler: Async callback for matching events

        Returns:
            Subscription ID
        """
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"

        async with self._lock:
            self._subscriptions[sub_id] = Subscription(
                id=sub_id,
                pattern=event_type,
                handler=handler,
            )

        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription."""
        async with self._lock:
            self._subscriptions.pop(subscription_id, None)

    async def close(self) -> None:
        """Mark bus as closed and clear subscriptions."""
        self._closed = True
        async with self._lock:
            self._subscriptions.clear()

    @property
    def subscription_count(self) -> int:
        """Number of active subscriptions."""
        return len(self._subscriptions)
