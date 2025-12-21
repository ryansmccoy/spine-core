"""Tests for spine.core.events.redis — RedisEventBus (mocked Redis).

Verifies the RedisEventBus class logic without requiring a real Redis
server by mocking the redis.asyncio module.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spine.core.events import Event
from spine.core.events.redis import RedisEventBus, Subscription


class TestRedisEventBusInit:
    def test_defaults(self):
        bus = RedisEventBus()
        assert bus._redis_url == "redis://localhost:6379"
        assert bus._channel_prefix == "spine:events"
        assert bus._subscriptions == {}
        assert bus._redis is None
        assert bus._closed is False

    def test_custom_url(self):
        bus = RedisEventBus("redis://custom:6380", channel_prefix="myapp")
        assert bus._redis_url == "redis://custom:6380"
        assert bus._channel_prefix == "myapp"


class TestSubscription:
    def test_dataclass(self):
        handler = AsyncMock()
        sub = Subscription(id="sub-1", pattern="run.*", handler=handler)
        assert sub.id == "sub-1"
        assert sub.pattern == "run.*"
        assert sub.handler is handler


class TestRedisEventBusConnect:
    @pytest.mark.asyncio
    async def test_connect_missing_redis_raises(self):
        bus = RedisEventBus()
        with patch.dict("sys.modules", {"redis.asyncio": None, "redis": None}):
            # The import will fail inside connect()
            with pytest.raises((ImportError, TypeError)):
                await bus.connect()


class TestRedisEventBusPublish:
    @pytest.mark.asyncio
    async def test_publish_not_connected_raises(self):
        bus = RedisEventBus()
        event = Event(event_type="test.event", source="unit-test")
        with pytest.raises(RuntimeError, match="not connected"):
            await bus.publish(event)

    @pytest.mark.asyncio
    async def test_publish_sends_json(self):
        bus = RedisEventBus()
        bus._redis = AsyncMock()

        event = Event(
            event_type="run.started",
            source="worker-1",
            payload={"run_id": "r1"},
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            correlation_id="corr-1",
            event_id="evt-1",
        )
        await bus.publish(event)

        bus._redis.publish.assert_called_once()
        channel, message = bus._redis.publish.call_args.args
        assert channel == "spine:events:run.started"
        data = json.loads(message)
        assert data["event_type"] == "run.started"
        assert data["source"] == "worker-1"
        assert data["correlation_id"] == "corr-1"


class TestRedisEventBusSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_returns_id(self):
        bus = RedisEventBus()
        handler = AsyncMock()
        sub_id = await bus.subscribe("run.*", handler)
        assert sub_id.startswith("redis_sub_")
        assert sub_id in bus._subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe_removes(self):
        bus = RedisEventBus()
        handler = AsyncMock()
        sub_id = await bus.subscribe("run.*", handler)
        await bus.unsubscribe(sub_id)
        assert sub_id not in bus._subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe_missing_is_noop(self):
        bus = RedisEventBus()
        await bus.unsubscribe("nonexistent")  # Should not raise


class TestRedisEventBusDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_calls_matching_handlers(self):
        bus = RedisEventBus()
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        await bus.subscribe("run.*", handler1)
        await bus.subscribe("operation.*", handler2)

        event = Event(event_type="run.started", source="test")
        await bus._dispatch(event)

        handler1.assert_called_once_with(event)
        handler2.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_handler_error_doesnt_propagate(self):
        bus = RedisEventBus()

        handler = AsyncMock(side_effect=RuntimeError("handler broke"))
        await bus.subscribe("run.*", handler)

        event = Event(event_type="run.completed", source="test")
        # Should not raise despite handler error
        await bus._dispatch(event)

    @pytest.mark.asyncio
    async def test_dispatch_no_matching_handlers(self):
        bus = RedisEventBus()
        handler = AsyncMock()
        await bus.subscribe("operation.*", handler)

        event = Event(event_type="run.started", source="test")
        await bus._dispatch(event)
        handler.assert_not_called()


class TestRedisEventBusClose:
    @pytest.mark.asyncio
    async def test_close_cleans_up(self):
        bus = RedisEventBus()
        bus._redis = AsyncMock()
        bus._pubsub = AsyncMock()
        bus._listener_task = None

        handler = AsyncMock()
        await bus.subscribe("run.*", handler)
        assert len(bus._subscriptions) == 1

        await bus.close()
        assert bus._closed is True
        assert bus._subscriptions == {}
        bus._pubsub.unsubscribe.assert_called_once()
        bus._redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_cancels_listener_task(self):
        bus = RedisEventBus()
        bus._redis = AsyncMock()
        bus._pubsub = AsyncMock()

        # Simulate a listener task via asyncio.Event
        started = asyncio.Event()

        async def fake_listener():
            started.set()
            await asyncio.sleep(3600)

        bus._listener_task = asyncio.create_task(fake_listener())
        await started.wait()  # ensure task is running
        await bus.close()
        assert bus._listener_task.cancelled() or bus._listener_task.done()
