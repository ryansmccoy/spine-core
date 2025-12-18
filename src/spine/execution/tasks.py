"""Celery task definitions for spine-core execution.

Provides the concrete Celery tasks that the :class:`CeleryExecutor` sends
work to.  A worker process running ``celery -A spine.execution.tasks worker``
will pick these up.

Setup::

    # Start a Celery worker:
    celery -A spine.execution.tasks worker --loglevel=info -Q default,high,low

    # Start Celery Beat (for scheduled runs):
    celery -A spine.execution.tasks beat --loglevel=info

Configuration::

    Set ``SPINE_CELERY_BROKER`` env var (default: ``redis://localhost:6379/0``).
    Set ``SPINE_CELERY_BACKEND`` env var (default: ``redis://localhost:6379/1``).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Celery app factory
# --------------------------------------------------------------------------- #

_BROKER = os.environ.get("SPINE_CELERY_BROKER", "redis://localhost:6379/0")
_BACKEND = os.environ.get("SPINE_CELERY_BACKEND", "redis://localhost:6379/1")

try:
    from celery import Celery

    app = Celery(
        "spine",
        broker=_BROKER,
        backend=_BACKEND,
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        # Default queue
        task_default_queue="default",
        # Priority queues
        task_queues={
            "realtime": {"exchange": "realtime", "routing_key": "realtime"},
            "high": {"exchange": "high", "routing_key": "high"},
            "default": {"exchange": "default", "routing_key": "default"},
            "low": {"exchange": "low", "routing_key": "low"},
            "slow": {"exchange": "slow", "routing_key": "slow"},
        },
    )

    CELERY_AVAILABLE = True

except ImportError:
    app = None  # type: ignore[assignment]
    CELERY_AVAILABLE = False
    logger.debug("Celery not installed — task definitions unavailable")


# --------------------------------------------------------------------------- #
# Handler resolution
# --------------------------------------------------------------------------- #


def _resolve_handler(kind: str, name: str):
    """Resolve a handler from the global registry."""
    from .registry import get_default_registry

    registry = get_default_registry()
    return registry.get(kind, name)


# --------------------------------------------------------------------------- #
# Task definitions
# --------------------------------------------------------------------------- #

if CELERY_AVAILABLE and app is not None:

    @app.task(name="spine.execute.task", bind=True, max_retries=3)
    def execute_task(
        self,
        name: str,
        params: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        parent_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a registered task handler.

        This is the Celery task that CeleryExecutor dispatches to.
        """
        logger.info("Celery executing task:%s with params=%s", name, params)
        try:
            handler = _resolve_handler("task", name)
            result = handler(params)
            return {"status": "completed", "result": result}
        except ValueError:
            logger.error("No handler registered for task:%s", name)
            raise
        except Exception as exc:
            logger.error("Task %s failed: %s", name, exc)
            # Retry with exponential backoff
            raise self.retry(exc=exc, countdown=2**self.request.retries)

    @app.task(name="spine.execute.pipeline", bind=True, max_retries=3)
    def execute_pipeline(
        self,
        name: str,
        params: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        parent_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a registered pipeline handler."""
        logger.info("Celery executing pipeline:%s", name)
        try:
            handler = _resolve_handler("pipeline", name)
            result = handler(params)
            return {"status": "completed", "result": result}
        except Exception as exc:
            logger.error("Pipeline %s failed: %s", name, exc)
            raise self.retry(exc=exc, countdown=2**self.request.retries)

    @app.task(name="spine.execute.workflow", bind=True, max_retries=3)
    def execute_workflow(
        self,
        name: str,
        params: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        parent_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a registered workflow handler."""
        logger.info("Celery executing workflow:%s", name)
        try:
            handler = _resolve_handler("workflow", name)
            result = handler(params)
            return {"status": "completed", "result": result}
        except Exception as exc:
            logger.error("Workflow %s failed: %s", name, exc)
            raise self.retry(exc=exc, countdown=2**self.request.retries)

    @app.task(name="spine.execute.step", bind=True, max_retries=3)
    def execute_step(
        self,
        name: str,
        params: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        parent_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a registered step handler."""
        logger.info("Celery executing step:%s", name)
        try:
            handler = _resolve_handler("step", name)
            result = handler(params)
            return {"status": "completed", "result": result}
        except Exception as exc:
            logger.error("Step %s failed: %s", name, exc)
            raise self.retry(exc=exc, countdown=2**self.request.retries)

else:
    # Stubs when Celery is not installed
    def execute_task(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery is not installed")

    def execute_pipeline(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery is not installed")

    def execute_workflow(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery is not installed")

    def execute_step(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery is not installed")
