"""
Events router — event bus introspection and management.

Provides endpoints for viewing recent events, subscribing to
event patterns, and checking event bus health.

Endpoints:
    GET  /events/status      Event bus status (backend, subscription count)
    POST /events/publish     Publish a test event (admin/debug)
    GET  /events/recent      List recent events from the in-memory buffer

Manifesto:
    Execution events should stream to consumers via SSE or polling
    so UIs and monitoring tools get near-real-time updates.

Tags:
    spine-core, api, events, lifecycle, streaming

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


# ------------------------------------------------------------------ #
# Server-Sent Events Stream
# ------------------------------------------------------------------ #


import asyncio
import fnmatch
import json
import logging

from fastapi import Query
from fastapi.responses import StreamingResponse

sse_logger = logging.getLogger(__name__)


def _glob_match(event_type: str, pattern: str) -> bool:
    """Check if an event type matches a glob pattern (e.g., 'run.*')."""
    return fnmatch.fnmatch(event_type, pattern)


@router.get("/stream")
async def event_stream(
    run_id: str | None = Query(None, description="Filter to specific run"),
    types: str | None = Query(None, description="Comma-separated event type patterns (e.g., 'run.*,step.*')"),
):
    """Server-Sent Events stream for real-time updates.

    Streams events as they occur in the system. Use for live
    dashboard updates, run progress tracking, and notifications.

    Supports optional filtering by run_id and event type patterns.
    Event type patterns support glob matching (e.g., 'run.*' matches
    'run.started', 'run.completed', etc.).

    This endpoint keeps the connection open and streams events in SSE format:
    ```
    data: {"event_id": "...", "event_type": "run.started", ...}

    data: {"event_id": "...", "event_type": "step.completed", ...}
    ```

    Args:
        run_id: Optional run ID to filter events for.
        types: Optional comma-separated event type patterns.

    Returns:
        SSE stream with events in JSON format.

    Example:
        GET /api/v1/events/stream?run_id=abc-123&types=run.*,step.*

        Response (SSE):
        data: {"event_id":"e1","event_type":"step.started","source":"worker","timestamp":"...","payload":{"step":"extract","run_id":"abc-123"}}

        data: {"event_id":"e2","event_type":"step.completed","source":"worker","timestamp":"...","payload":{"step":"extract","duration_ms":3200}}
    """
    from spine.core.events import Event, get_event_bus

    bus = get_event_bus()
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
    type_filters = [t.strip() for t in types.split(",")] if types else None

    def matches(event: Event) -> bool:
        """Check if event matches filters."""
        # Filter by run_id if specified
        if run_id:
            event_run_id = event.payload.get("run_id") if event.payload else None
            if event_run_id != run_id:
                return False
        # Filter by event type pattern if specified
        if type_filters:
            return any(_glob_match(event.event_type, pattern) for pattern in type_filters)
        return True

    async def on_event(event: Event) -> None:
        """Callback for event bus subscription."""
        if matches(event):
            try:
                # Use put_nowait to avoid blocking if queue is full
                queue.put_nowait(event)
            except asyncio.QueueFull:
                sse_logger.warning("SSE queue full, dropping event %s", event.event_id)

    # Subscribe to all events, filter in callback
    sub_id = await bus.subscribe("*", on_event)

    async def generate():
        """Generate SSE stream."""
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'event_type': 'connected', 'message': 'SSE stream connected'})}\n\n"

            while True:
                try:
                    # Wait for events with timeout (heartbeat every 30s)
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    data = {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "source": event.source,
                        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                        "payload": event.payload or {},
                        "correlation_id": event.correlation_id,
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat comment to keep connection alive
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            sse_logger.debug("SSE stream cancelled")
        finally:
            # Clean up subscription
            try:
                await bus.unsubscribe(sub_id)
            except Exception:
                pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )