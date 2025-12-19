"""Pipeline registry for registering and discovering pipelines."""

from collections.abc import Callable
from typing import TYPE_CHECKING

from spine.core.logging import get_logger

if TYPE_CHECKING:
    from spine.framework.pipelines import Pipeline

logger = get_logger()

# Global pipeline registry
_registry: dict[str, type["Pipeline"]] = {}
_loaded: bool = False


def register_pipeline(name: str) -> Callable[[type["Pipeline"]], type["Pipeline"]]:
    """Decorator to register a pipeline class."""

    def decorator(cls: type["Pipeline"]) -> type["Pipeline"]:
        if name in _registry:
            raise ValueError(f"Pipeline '{name}' is already registered")
        _registry[name] = cls
        # Get description from class if available
        description = getattr(cls, "description", "No description available")
        logger.debug(
            "pipeline_registered",
            name=name,
            cls=cls.__name__,
            description=description,
        )
        return cls

    return decorator


def _ensure_loaded() -> None:
    """Ensure pipelines are loaded (lazy initialization)."""
    global _loaded
    if not _loaded:
        _load_pipelines()
        _loaded = True


def get_pipeline(name: str) -> type["Pipeline"]:
    """Get a pipeline class by name."""
    _ensure_loaded()
    if name not in _registry:
        available = ", ".join(_registry.keys())
        raise KeyError(f"Pipeline '{name}' not found. Available: {available}")
    return _registry[name]


def list_pipelines() -> list[str]:
    """List all registered pipeline names."""
    _ensure_loaded()
    return sorted(_registry.keys())


def clear_registry() -> None:
    """Clear registry (for testing)."""
    global _loaded
    _registry.clear()
    _loaded = False


def _load_pipelines() -> None:
    """
    Load all pipeline modules to trigger registration.

    Domain pipelines register via @register_pipeline decorator.
    When domain packages (e.g., spine-domains-finra) are installed,
    they auto-register their pipelines on import.

    To add a new domain:
    1. Install the domain package (e.g., pip install spine-domains-finra)
    2. Import the domain's pipelines module
    3. Pipelines auto-register via @register_pipeline decorator

    Note: This is called lazily by _ensure_loaded() to ensure logging
    is configured before registration messages are emitted.
    """
    # Domain pipeline discovery via entry points (future: use importlib.metadata)
    # For now, pipelines register when their modules are imported by the consumer.
    logger.debug("pipeline_registry_loaded", registered=len(_registry))
