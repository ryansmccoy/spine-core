"""Pipeline registry for registering and discovering pipelines."""

from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from spine.framework.pipelines import Pipeline

logger = structlog.get_logger()

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

    Pipelines are explicitly imported from spine.domains (shared library).
    Each domain module should use @register_pipeline decorator.

    To add a new domain:
    1. Create src/spine/domains/{domain_family}/{dataset}/pipelines.py
    2. Add explicit import below (e.g., import spine.domains.finra.trace.pipelines)
    3. Pipelines will auto-register via @register_pipeline decorator

    Note: This is called lazily by _ensure_loaded() to ensure logging
    is configured before registration messages are emitted.
    """
    # Import canonical domain pipelines from spine.domains (shared library)
    # These are the cross-tier shareable implementations

    # FINRA OTC Transparency domain
    try:
        import spine.domains.finra.otc_transparency.pipelines  # noqa: F401

        logger.debug("domain_pipelines_loaded", domain="finra.otc_transparency")
    except ImportError as e:
        logger.warning("domain_pipelines_not_found", domain="finra.otc_transparency", error=str(e))

    # Reference Data: Exchange Calendar domain
    try:
        import spine.domains.reference.exchange_calendar.pipelines  # noqa: F401

        logger.debug("domain_pipelines_loaded", domain="reference.exchange_calendar")
    except ImportError as e:
        logger.warning("domain_pipelines_not_found", domain="reference.exchange_calendar", error=str(e))

    # Market Data: Price data from external sources
    try:
        import spine.domains.market_data.pipelines  # noqa: F401

        logger.debug("domain_pipelines_loaded", domain="market_data")
    except ImportError as e:
        logger.warning("domain_pipelines_not_found", domain="market_data", error=str(e))

