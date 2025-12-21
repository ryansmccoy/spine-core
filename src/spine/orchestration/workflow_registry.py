"""Workflow Registry — global registration and discovery of workflows.

Manifesto:
Large applications define workflows in many modules.  The registry
provides a single lookup table so that runners, CLIs, and APIs can
find workflows by name without knowing which module defined them.

ARCHITECTURE
────────────
::

    register_workflow(workflow_or_factory)   → stores in global dict
    get_workflow(name)                       → returns Workflow or raises
    list_workflows(domain=None)             → names, optionally filtered
    clear_workflow_registry()               → reset (for testing)

    WorkflowNotFoundError  ── raised when get_workflow fails

BEST PRACTICES
──────────────
- Call ``clear_workflow_registry()`` in test fixtures to avoid leaks.
- Use domain-based naming (``"finra.otc.ingest"``) for discoverability.
- ``register_workflow`` accepts both a ``Workflow`` instance and a
  zero-arg factory function (decorated or direct).

Related modules:
    workflow.py        — the Workflow dataclass being registered
    workflow_runner.py — executes registered workflows

Example::

    from spine.orchestration.workflow_registry import (
        register_workflow, get_workflow, list_workflows, clear_workflow_registry,
    )

    register_workflow(my_workflow)
    workflow = get_workflow("ingest.daily")
    names = list_workflows(domain="ingest")

Tags:
    spine-core, orchestration, registry, discovery, lookup

Doc-Types:
    api-reference
"""

from __future__ import annotations

from collections.abc import Callable

from spine.core.logging import get_logger
from spine.orchestration.exceptions import GroupError
from spine.orchestration.workflow import Workflow

logger = get_logger(__name__)

# Global workflow registry
_registry: dict[str, Workflow] = {}
_loaded: bool = False


class WorkflowNotFoundError(GroupError):
    """Raised when a workflow is not found in the registry."""

    def __init__(self, name: str) -> None:
        self.workflow_name = name
        available = ", ".join(sorted(_registry.keys())) if _registry else "(none)"
        super().__init__(
            f"Workflow '{name}' not found. Available: {available}"
        )


def register_workflow(
    workflow_or_factory: Workflow | Callable[[], Workflow],
) -> Workflow:
    """
    Register a workflow.

    Can be called with a Workflow instance directly, or used as a
    decorator on a factory function that returns a Workflow.

    Args:
        workflow_or_factory: Workflow instance or factory function

    Returns:
        The registered Workflow

    Raises:
        ValueError: If a workflow with the same name is already registered
        TypeError: If the argument is not a Workflow

    Examples:
        # Direct registration
        wf = Workflow(name="my.workflow", steps=[...])
        register_workflow(wf)

        # As decorator
        @register_workflow
        def my_workflow():
            return Workflow(name="my.workflow", steps=[...])
    """
    if callable(workflow_or_factory) and not isinstance(workflow_or_factory, Workflow):
        workflow = workflow_or_factory()
    else:
        workflow = workflow_or_factory

    if not isinstance(workflow, Workflow):
        raise TypeError(
            f"Expected Workflow, got {type(workflow).__name__}. "
            "If using as decorator, the function must return a Workflow."
        )

    if workflow.name in _registry:
        raise ValueError(f"Workflow '{workflow.name}' is already registered")

    _registry[workflow.name] = workflow

    logger.debug(
        "workflow_registered",
        name=workflow.name,
        domain=workflow.domain,
        step_count=len(workflow.steps),
    )

    return workflow


def get_workflow(name: str) -> Workflow:
    """
    Get a workflow by name.

    Args:
        name: The workflow name

    Returns:
        The registered Workflow

    Raises:
        WorkflowNotFoundError: If the workflow is not registered
    """
    _ensure_loaded()

    if name not in _registry:
        raise WorkflowNotFoundError(name)

    return _registry[name]


def list_workflows(domain: str | None = None) -> list[str]:
    """
    List all registered workflow names.

    Args:
        domain: Optional filter by domain

    Returns:
        Sorted list of workflow names
    """
    _ensure_loaded()

    if domain:
        return sorted(
            name for name, wf in _registry.items() if wf.domain == domain
        )
    return sorted(_registry.keys())


def workflow_exists(name: str) -> bool:
    """Check if a workflow is registered."""
    _ensure_loaded()
    return name in _registry


def clear_workflow_registry() -> None:
    """
    Clear the workflow registry.

    Primarily for testing — allows tests to start with a clean registry.
    """
    global _loaded
    _registry.clear()
    _loaded = False
    logger.debug("workflow_registry_cleared")


def _ensure_loaded() -> None:
    """
    Ensure workflows are loaded (lazy initialization).

    Mirrors the pattern from the group registry.
    Future phases will load workflows from YAML files or database.
    """
    global _loaded
    if not _loaded:
        _load_workflows()
        _loaded = True


def _load_workflows() -> None:
    """
    Load workflows from configured sources.

    Currently a no-op (workflows registered via Python DSL).
    Future: Load from YAML files via workflow_yaml module.
    """
    pass


def get_workflow_registry_stats() -> dict:
    """Get statistics about the registry (for debugging/health checks)."""
    _ensure_loaded()

    domains: dict[str, int] = {}
    for wf in _registry.values():
        domain = wf.domain or "(no domain)"
        domains[domain] = domains.get(domain, 0) + 1

    return {
        "total_workflows": len(_registry),
        "workflows_by_domain": domains,
    }
