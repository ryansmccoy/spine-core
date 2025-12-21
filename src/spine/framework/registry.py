"""Operation registry for registering and discovering operations.

Manifesto:
    A central registry lets code discover operations at runtime
    (by name, tag, or domain) without import-time coupling.

Tags:
    spine-core, framework, registry, operation-discovery, lookup

Doc-Types:
    api-reference
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from spine.core.logging import get_logger

if TYPE_CHECKING:
    from spine.framework.operations import Operation

logger = get_logger()

# Global operation registry
_registry: dict[str, type["Operation"]] = {}
_loaded: bool = False


def register_operation(name: str) -> Callable[[type["Operation"]], type["Operation"]]:
    """Decorator to register a operation class."""

    def decorator(cls: type["Operation"]) -> type["Operation"]:
        if name in _registry:
            raise ValueError(f"Operation '{name}' is already registered")
        _registry[name] = cls
        # Get description from class if available
        description = getattr(cls, "description", "No description available")
        logger.debug(
            "operation_registered",
            name=name,
            cls=cls.__name__,
            description=description,
        )
        return cls

    return decorator


def _ensure_loaded() -> None:
    """Ensure operations are loaded (lazy initialization)."""
    global _loaded
    if not _loaded:
        _load_operations()
        _loaded = True


def get_operation(name: str) -> type["Operation"]:
    """Get a operation class by name."""
    _ensure_loaded()
    if name not in _registry:
        available = ", ".join(_registry.keys())
        raise KeyError(f"Operation '{name}' not found. Available: {available}")
    return _registry[name]


def list_operations() -> list[str]:
    """List all registered operation names."""
    _ensure_loaded()
    return sorted(_registry.keys())


def clear_registry() -> None:
    """Clear registry (for testing)."""
    global _loaded
    _registry.clear()
    _loaded = False


def _load_operations() -> None:
    """
    Load all operation modules to trigger registration.

    Domain operations register via @register_operation decorator.
    When domain packages (e.g., spine-domains-finra) are installed,
    they auto-register their operations on import.

    To add a new domain:
    1. Install the domain package (e.g., pip install spine-domains-finra)
    2. Import the domain's operations module
    3. Operations auto-register via @register_operation decorator

    Note: This is called lazily by _ensure_loaded() to ensure logging
    is configured before registration messages are emitted.
    """
    # Domain operation discovery via entry points (future: use importlib.metadata)
    # For now, operations register when their modules are imported by the consumer.
    logger.debug("operation_registry_loaded", registered=len(_registry))
