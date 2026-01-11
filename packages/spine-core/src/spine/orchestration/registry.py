"""
Pipeline Group Registry - Registration and lookup for pipeline groups.

Follows the same patterns as spine.framework.registry for pipelines:
- Global registry with module-level functions
- Decorator or direct registration
- Lazy loading support
- Clear for testing

Usage:
    from spine.orchestration import register_group, get_group, list_groups

    # Register a group
    register_group(my_group)

    # Or use decorator (for Python DSL)
    @register_group
    def my_group():
        return PipelineGroup(...)

    # Lookup
    group = get_group("finra.weekly_refresh")

    # List all
    names = list_groups()
"""

from typing import Callable

import structlog

from spine.orchestration.models import PipelineGroup
from spine.orchestration.exceptions import GroupNotFoundError

logger = structlog.get_logger()

# Global group registry
_registry: dict[str, PipelineGroup] = {}
_loaded: bool = False


def register_group(
    group_or_factory: PipelineGroup | Callable[[], PipelineGroup],
) -> PipelineGroup:
    """
    Register a pipeline group.

    Can be called with a PipelineGroup instance directly, or used as a
    decorator on a factory function that returns a PipelineGroup.

    Args:
        group_or_factory: PipelineGroup instance or factory function

    Returns:
        The registered PipelineGroup

    Raises:
        ValueError: If a group with the same name is already registered

    Examples:
        # Direct registration
        group = PipelineGroup(name="my.group", steps=[...])
        register_group(group)

        # As decorator
        @register_group
        def my_group():
            return PipelineGroup(name="my.group", steps=[...])
    """
    if callable(group_or_factory) and not isinstance(group_or_factory, PipelineGroup):
        # It's a factory function - call it to get the group
        group = group_or_factory()
    else:
        group = group_or_factory

    if not isinstance(group, PipelineGroup):
        raise TypeError(
            f"Expected PipelineGroup, got {type(group).__name__}. "
            "If using as decorator, the function must return a PipelineGroup."
        )

    if group.name in _registry:
        raise ValueError(f"Pipeline group '{group.name}' is already registered")

    _registry[group.name] = group

    logger.debug(
        "group_registered",
        name=group.name,
        domain=group.domain,
        step_count=len(group.steps),
    )

    return group


def get_group(name: str) -> PipelineGroup:
    """
    Get a pipeline group by name.

    Args:
        name: The group name

    Returns:
        The registered PipelineGroup

    Raises:
        GroupNotFoundError: If the group is not registered
    """
    _ensure_loaded()

    if name not in _registry:
        available = ", ".join(sorted(_registry.keys())) if _registry else "(none)"
        raise GroupNotFoundError(name)

    return _registry[name]


def list_groups(domain: str | None = None) -> list[str]:
    """
    List all registered group names.

    Args:
        domain: Optional filter by domain

    Returns:
        Sorted list of group names
    """
    _ensure_loaded()

    if domain:
        return sorted(
            name for name, group in _registry.items()
            if group.domain == domain
        )
    return sorted(_registry.keys())


def group_exists(name: str) -> bool:
    """Check if a group is registered."""
    _ensure_loaded()
    return name in _registry


def clear_group_registry() -> None:
    """
    Clear the group registry.

    Primarily for testing - allows tests to start with a clean registry.
    """
    global _loaded
    _registry.clear()
    _loaded = False
    logger.debug("group_registry_cleared")


def _ensure_loaded() -> None:
    """
    Ensure groups are loaded (lazy initialization).

    This mirrors the pattern from spine.framework.registry._ensure_loaded().
    In future phases, this will load groups from YAML files or database.
    """
    global _loaded
    if not _loaded:
        _load_groups()
        _loaded = True


def _load_groups() -> None:
    """
    Load pipeline groups from configured sources.

    Phase 1: No-op (groups registered via Python DSL)
    Phase 2+: Load from YAML files and/or database
    """
    # TODO (Phase 2): Load from YAML files in groups/ directory
    # TODO (Phase 2): Load from database if group_storage=database
    pass


def get_registry_stats() -> dict:
    """Get statistics about the registry (for debugging/health checks)."""
    _ensure_loaded()

    domains = {}
    for group in _registry.values():
        domain = group.domain or "(no domain)"
        domains[domain] = domains.get(domain, 0) + 1

    return {
        "total_groups": len(_registry),
        "groups_by_domain": domains,
    }
