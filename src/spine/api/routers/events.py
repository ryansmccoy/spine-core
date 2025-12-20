"""
Events router — event bus introspection and management.

Provides endpoints for viewing recent events, subscribing to
event patterns, and checking event bus health.

Endpoints:
    GET  /events/status      Event bus status (backend, subscription count)
    POST /events/publish     Publish a test event (admin/debug)
    GET  /events/recent      List recent events from the in-memory buffer

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/events")


# ------------------------------------------------------------------ #
# Pydantic Schemas
# ------------------------------------------------------------------ #


class EventBusStatusResponse(BaseModel):
    """Event bus status."""

    backend: str = "unknown"
    subscription_count: int = 0
    closed: bool = False


class PublishEventRequest(BaseModel):
    """Request body for publishing a test event."""

    event_type: str = Field(..., description="Dot-separated event type")
    source: str = Field(default="api", description="Event source identifier")
    payload: dict[str, Any] = Field(default_factory=dict, description="Event payload")
    correlation_id: str | None = Field(default=None, description="Correlation ID for tracing")


class PublishEventResponse(BaseModel):
    """Response from publishing an event."""

    success: bool = True
    event_id: str = ""
    event_type: str = ""


class RecentEventSchema(BaseModel):
    """A recently published event."""

    event_id: str
    event_type: str
    source: str
    payload: dict[str, Any] = {}
    timestamp: str | None = None
    correlation_id: str | None = None


# ------------------------------------------------------------------ #
# Event Bus Status
# ------------------------------------------------------------------ #


@router.get("/status", response_model=EventBusStatusResponse)
async def get_event_bus_status() -> EventBusStatusResponse:
    """Get event bus backend status and subscription count."""
    from spine.core.events import get_event_bus

    bus = get_event_bus()
    backend = type(bus).__name__

    sub_count = 0
    if hasattr(bus, "subscription_count"):
        sub_count = bus.subscription_count

    closed = getattr(bus, "_closed", False)

    return EventBusStatusResponse(
        backend=backend,
        subscription_count=sub_count,
        closed=closed,
    )


# ------------------------------------------------------------------ #
# Publish (debug / testing)
# ------------------------------------------------------------------ #


@router.post("/publish", response_model=PublishEventResponse)
async def publish_event(body: PublishEventRequest) -> PublishEventResponse:
    """Publish an event to the bus (for testing/debugging)."""
    from spine.core.events import Event, get_event_bus

    event = Event(
        event_type=body.event_type,
        source=body.source,
        payload=body.payload,
        correlation_id=body.correlation_id,
    )

    bus = get_event_bus()
    await bus.publish(event)

    return PublishEventResponse(
        success=True,
        event_id=event.event_id,
        event_type=event.event_type,
    )
