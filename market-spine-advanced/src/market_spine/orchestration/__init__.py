"""Orchestration components."""

from market_spine.orchestration.backends.protocol import OrchestratorBackend
from market_spine.orchestration.backends.local import LocalBackend
from market_spine.orchestration.backends.celery_backend import CeleryBackend
from market_spine.orchestration.dlq import DLQManager
from market_spine.orchestration.scheduler import ScheduleManager

_backend_instance: OrchestratorBackend | None = None


def get_backend() -> OrchestratorBackend:
    """Get the configured backend instance."""
    global _backend_instance

    if _backend_instance is None:
        from market_spine.config import get_settings

        settings = get_settings()

        if settings.celery_broker_url:
            _backend_instance = CeleryBackend()
        else:
            _backend_instance = LocalBackend()

    return _backend_instance


def set_backend(backend: OrchestratorBackend) -> None:
    """Set the backend instance (useful for testing)."""
    global _backend_instance
    _backend_instance = backend


__all__ = [
    "OrchestratorBackend",
    "LocalBackend",
    "CeleryBackend",
    "DLQManager",
    "ScheduleManager",
    "get_backend",
    "set_backend",
]
