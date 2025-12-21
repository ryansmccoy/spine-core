"""Tests for spine.core.events — Event model, EventBus protocol, InMemoryEventBus."""

import asyncio

import pytest

from spine.core.events import Event, EventBus, get_event_bus, set_event_bus
from spine.core.events.memory import InMemoryEventBus


# ------------------------------------------------------------------ #
# Event model
# ------------------------------------------------------------------ #


class TestEvent:
    def test_defaults(self):
        event = Event(event_type="run.started", source="test")
        assert event.event_type == "run.started"
        assert event.source == "test"
        assert event.payload == {}
        assert event.event_id  # auto-generated
        assert event.timestamp  # auto-generated

    def test_with_payload(self):
        event = Event(
            event_type="run.completed",
            source="operation",
            payload={"run_id": "r1", "status": "success"},
        )
        assert event.payload["run_id"] == "r1"

    def test_correlation_id(self):
        event = Event(
            event_type="run.started",
            source="test",
            correlation_id="corr-123",
        )
        assert event.correlation_id == "corr-123"

    def test_unique_ids(self):
        e1 = Event(event_type="test", source="test")
        e2 = Event(event_type="test", source="test")
        assert e1.event_id != e2.event_id


class TestEventMatches:
    def test_exact_match(self):
        event = Event(event_type="run.started", source="test")
        assert event.matches("run.started") is True
        assert event.matches("run.completed") is False

    def test_wildcard_all(self):
        event = Event(event_type="run.started", source="test")
        assert event.matches("*") is True

    def test_prefix_wildcard(self):
        event = Event(event_type="run.started", source="test")
        assert event.matches("run.*") is True
        assert event.matches("workflow.*") is False

    def test_no_partial_match(self):
        event = Event(event_type="run.started.extra", source="test")
        # run.* should match run.started.extra because it starts with "run."
        assert event.matches("run.*") is True
        assert event.matches("run.started.*") is True


# ------------------------------------------------------------------ #
# InMemoryEventBus
# ------------------------------------------------------------------ #


class TestInMemoryEventBus:
    @pytest.fixture
    def bus(self):
        return InMemoryEventBus()

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self, bus):
        """Publishing to empty bus should not raise."""
        event = Event(event_type="test", source="test")
        await bus.publish(event)

    @pytest.mark.asyncio
    async def test_subscribe_and_receive(self, bus):
        received = []

        async def handler(event: Event):
            received.append(event)

        await bus.subscribe("test.*", handler)
        await bus.publish(Event(event_type="test.hello", source="test"))

        assert len(received) == 1
        assert received[0].event_type == "test.hello"

    @pytest.mark.asyncio
    async def test_exact_match_subscribe(self, bus):
        received = []

        async def handler(event: Event):
            received.append(event)

        await bus.subscribe("run.completed", handler)
        await bus.publish(Event(event_type="run.started", source="test"))
        await bus.publish(Event(event_type="run.completed", source="test"))

        assert len(received) == 1
        assert received[0].event_type == "run.completed"

    @pytest.mark.asyncio
    async def test_wildcard_subscribe(self, bus):
        received = []

        async def handler(event: Event):
            received.append(event)

        await bus.subscribe("*", handler)
        await bus.publish(Event(event_type="run.started", source="test"))
        await bus.publish(Event(event_type="workflow.failed", source="test"))

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        received = []

        async def handler(event: Event):
            received.append(event)

        sub_id = await bus.subscribe("test.*", handler)
        await bus.publish(Event(event_type="test.one", source="test"))
        assert len(received) == 1

        await bus.unsubscribe(sub_id)
        await bus.publish(Event(event_type="test.two", source="test"))
        assert len(received) == 1  # No new events after unsubscribe

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, bus):
        received_a = []
        received_b = []

        async def handler_a(event: Event):
            received_a.append(event)

        async def handler_b(event: Event):
            received_b.append(event)

        await bus.subscribe("test.*", handler_a)
        await bus.subscribe("test.*", handler_b)
        await bus.publish(Event(event_type="test.hello", source="test"))

        assert len(received_a) == 1
        assert len(received_b) == 1

    @pytest.mark.asyncio
    async def test_handler_error_does_not_stop_delivery(self, bus):
        received = []

        async def bad_handler(event: Event):
            raise ValueError("Boom!")

        async def good_handler(event: Event):
            received.append(event)

        await bus.subscribe("test.*", bad_handler)
        await bus.subscribe("test.*", good_handler)
        await bus.publish(Event(event_type="test.hello", source="test"))

        # Good handler should still have received the event
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_close(self, bus):
        received = []

        async def handler(event: Event):
            received.append(event)

        await bus.subscribe("test.*", handler)
        await bus.close()

        # After close, publish should be a no-op
        await bus.publish(Event(event_type="test.hello", source="test"))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_subscription_count(self, bus):
        async def handler(event: Event):
            pass

        assert bus.subscription_count == 0
        sub1 = await bus.subscribe("a.*", handler)
        assert bus.subscription_count == 1
        sub2 = await bus.subscribe("b.*", handler)
        assert bus.subscription_count == 2
        await bus.unsubscribe(sub1)
        assert bus.subscription_count == 1


# ------------------------------------------------------------------ #
# Global singleton
# ------------------------------------------------------------------ #


class TestGlobalEventBus:
    def test_get_default(self):
        # Reset global state
        set_event_bus(None)  # type: ignore[arg-type]
        bus = get_event_bus()
        assert isinstance(bus, InMemoryEventBus)

    def test_set_and_get(self):
        custom_bus = InMemoryEventBus()
        set_event_bus(custom_bus)
        assert get_event_bus() is custom_bus
        # Cleanup
        set_event_bus(None)  # type: ignore[arg-type]


# ------------------------------------------------------------------ #
# Protocol conformance
# ------------------------------------------------------------------ #


class TestEventBusProtocol:
    def test_in_memory_implements_protocol(self):
        bus = InMemoryEventBus()
        assert isinstance(bus, EventBus)
