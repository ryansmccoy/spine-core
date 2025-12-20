"""Webhook trigger endpoints for spine-core.

Provides HTTP POST endpoints that trigger registered workflows or
pipelines.  External systems (GitHub, Slack, monitoring tools, cron
services) can call these endpoints to kick off spine execution.

Endpoints
---------
``GET  /webhooks``                  — list registered webhook targets
``POST /webhooks/trigger/{name}``   — trigger a workflow or pipeline

Setup::

    from spine.ops.webhooks import register_webhook
    from spine.api.routers.webhooks import router as webhook_router

    # Register targets at startup
    register_webhook("sec.daily_ingest", kind="workflow")
    register_webhook("finra.otc_download", kind="pipeline")

    # Include in FastAPI app
    app.include_router(webhook_router, prefix="/api/v1", tags=["webhooks"])
"""

from __future__ import annotations

from typing import Any

from spine.core.logging import get_logger
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from spine.ops.webhooks import (
    WebhookTarget,
    clear_webhooks,  # noqa: F401 — re-exported for backward compat
    get_webhook_target,
    list_registered_webhooks,
    register_webhook,  # noqa: F401 — re-exported for backward compat
)

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── Models ───────────────────────────────────────────────────────────


class WebhookResponse(BaseModel):
    """Response returned after a webhook trigger."""

    run_id: str
    name: str
    kind: str
    status: str = "submitted"


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/", response_model=list[WebhookTarget])
async def list_webhooks() -> list[WebhookTarget]:
    """List all registered webhook targets."""
    return list_registered_webhooks()


@router.post("/trigger/{name}", response_model=WebhookResponse)
async def trigger_webhook(name: str, request: Request) -> WebhookResponse:
    """Trigger a registered workflow or pipeline via webhook.

    The JSON request body (if any) is passed as ``params`` to the
    workflow / pipeline.

    Args:
        name: Registered target name.

    Returns:
        :class:`WebhookResponse` with the ``run_id`` and submission status.

    Raises:
        HTTPException 404: Target not registered.
        HTTPException 503: Dispatcher not wired into app state.
    """
    target = get_webhook_target(name)
    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Webhook target '{name}' not found. "
            f"Registered targets: {', '.join(t.name for t in list_registered_webhooks()) or '(none)'}",
        )

    # Parse body — tolerate empty or non-JSON bodies
    body: dict[str, Any] = {}
    try:
        raw = await request.body()
        if raw:
            body = await request.json()
    except Exception:
        body = {}

    # Resolve the EventDispatcher from app state
    from spine.execution.dispatcher import EventDispatcher
    from spine.execution.spec import pipeline_spec, workflow_spec

    dispatcher: EventDispatcher | None = getattr(request.app.state, "dispatcher", None)
    if not dispatcher:
        raise HTTPException(
            status_code=503,
            detail="EventDispatcher not configured on app.state.dispatcher",
        )

    if target.kind == "workflow":
        spec = workflow_spec(name, params=body, trigger_source="webhook")
    else:
        spec = pipeline_spec(name, params=body, trigger_source="webhook")

    run_id = await dispatcher.submit(spec)

    logger.info("webhook.triggered", name=name, kind=target.kind, run_id=run_id)

    return WebhookResponse(run_id=run_id, name=name, kind=target.kind)
