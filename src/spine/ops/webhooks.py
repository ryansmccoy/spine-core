"""
Webhook registry — manage webhook targets for workflows and pipelines.

Extracted from ``api/routers/webhooks.py`` so that both CLI and API
can share the same registry without cross-layer imports
(SMELL-LAYER-0004).

Doc-Types: OPS_MODULE
"""

from __future__ import annotations

from dataclasses import dataclass

from spine.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WebhookTarget:
    """A workflow or pipeline exposed as a webhook target."""

    name: str = ""
    kind: str = "workflow"  # "workflow" | "pipeline"
    description: str = ""


# ── In-process registry ──────────────────────────────────────────────

_targets: dict[str, WebhookTarget] = {}


def register_webhook(
    name: str,
    kind: str = "workflow",
    description: str = "",
) -> None:
    """Register a workflow or pipeline as a webhook target.

    Args:
        name: Registered workflow or pipeline name.
        kind: ``"workflow"`` or ``"pipeline"``.
        description: Human-readable description shown in ``GET /webhooks``.
    """
    _targets[name] = WebhookTarget(name=name, kind=kind, description=description)
    logger.info("webhook.registered", name=name, kind=kind)


def clear_webhooks() -> None:
    """Remove all webhook registrations (useful in tests)."""
    _targets.clear()


def list_registered_webhooks() -> list[WebhookTarget]:
    """Return a copy of all registered webhook targets."""
    return list(_targets.values())


def get_webhook_target(name: str) -> WebhookTarget | None:
    """Look up a single webhook target by name."""
    return _targets.get(name)
