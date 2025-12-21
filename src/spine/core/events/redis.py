"""
Redis Pub/Sub event bus implementation.

Manifesto:
    Multi-node deployments need events to cross process boundaries.
    Redis Pub/Sub provides fire-and-forget delivery with minimal latency
    and no schema overhead.

Uses Redis Pub/Sub for multi-node deployments. Events are delivered
asynchronously and not persisted (use Redis Streams for persistence).

Requires: ``pip install redis`` or ``spine-core[redis]``

Tags:
    spine-core, events, redis, pub-sub, multi-node, async, import-guarded

Doc-Types:
    api-reference
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from spine.core.events import Event, EventHandler

__all__ = ["RedisEventBus"]


@dataclass
class Subscription:
    """Internal subscription record."""

    id: str
    pattern: str
    handler: EventHandler


class RedisEventBus:
    """Redis Pub/Sub backend for multi-node deployments.

    Events are published to Redis channels and delivered to all
    subscribers across nodes. Patterns are handled client-side.

    Example::

        bus = RedisEventBus("redis://localhost:6379")
        await bus.connect()

        async def log_event(event: Event):
            print(f"Event: {event.event_type}")

        await bus.subscribe("run.*", log_event)
        await bus.publish(Event(event_type="run.started", source="worker"))
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        *,
        channel_prefix: str = "spine:events",
    ) -> None:
        self._redis_url = redis_url
        self._channel_prefix = channel_prefix
        self._subscriptions: dict[str, Subscription] = {}
        self._redis: Any = None
        self._pubsub: Any = None
        self._listener_task: asyncio.Task | None = None
        self._closed = False

    async def connect(self) -> None:
        """Connect to Redis and start listening for events."""
        try:
            import redis.asyncio as aioredis
        except ImportError as e:
            raise ImportError(
                "redis package required for RedisEventBus. "
                "Install with: pip install redis"
            ) from e

        self._redis = aioredis.from_url(self._redis_url)
        self._pubsub = self._redis.pubsub()

        # Subscribe to the spine events channel
        await self._pubsub.subscribe(f"{self._channel_prefix}:*")

        # Start background listener
        self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        """Background task to receive and dispatch events."""
        from spine.core.logging import get_logger
        log = get_logger("spine.events.redis")

        try:
            async for message in self._pubsub.listen():
                if self._closed:
                    break

                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                    event = Event(
                        event_type=data["event_type"],
                        source=data["source"],
                        payload=data.get("payload", {}),
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        correlation_id=data.get("correlation_id"),
                        event_id=data.get("event_id", str(uuid.uuid4())),
                    )

                    # Dispatch to matching handlers
                    await self._dispatch(event)

                except Exception as e:
                    log.warning("event_parse_error", error=str(e))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("event_listener_error", error=str(e))

    async def _dispatch(self, event: Event) -> None:
        """Dispatch event to matching handlers."""
        handlers_to_call: list[tuple[str, EventHandler]] = []

        for sub in self._subscriptions.values():
            if event.matches(sub.pattern):
                handlers_to_call.append((sub.id, sub.handler))

        if not handlers_to_call:
            return

        async def safe_call(sub_id: str, handler: EventHandler) -> None:
            try:
                await handler(event)
            except Exception as e:
                from spine.core.logging import get_logger
                log = get_logger("spine.events.redis")
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

    async def publish(self, event: Event) -> None:
        """Publish an event to Redis."""
        if self._redis is None:
            raise RuntimeError("RedisEventBus not connected. Call connect() first.")

        message = json.dumps({
            "event_type": event.event_type,
            "source": event.source,
            "payload": event.payload,
            "timestamp": event.timestamp.isoformat(),
            "correlation_id": event.correlation_id,
            "event_id": event.event_id,
        })

        channel = f"{self._channel_prefix}:{event.event_type}"
        await self._redis.publish(channel, message)

    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> str:
        """Subscribe to events matching a pattern."""
        sub_id = f"redis_sub_{uuid.uuid4().hex[:12]}"

        self._subscriptions[sub_id] = Subscription(
            id=sub_id,
            pattern=event_type,
            handler=handler,
        )

        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription."""
        self._subscriptions.pop(subscription_id, None)

    async def close(self) -> None:
        """Close Redis connections and stop listener."""
        self._closed = True

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()

        self._subscriptions.clear()
