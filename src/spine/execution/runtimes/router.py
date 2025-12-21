"""Runtime adapter router — selects the right adapter for each job.

The ``RuntimeAdapterRouter`` maintains a registry of named runtime adapters
and routes ``ContainerJobSpec`` submissions to the appropriate one based on
explicit ``spec.runtime`` hints or automatic capability matching.

Architecture:

    .. code-block:: text

        RuntimeAdapterRouter — Adapter Registry + Router
        ┌──────────────────────────────────────────────────────────────┐
        │                                                              │
        │  Registry                                                    │
        │  ────────                                                    │
        │  register(adapter)       → stores by adapter.runtime_name    │
        │  unregister(name)        → removes adapter                   │
        │  get(name)               → exact lookup by name              │
        │  list_runtimes()         → all registered names              │
        │                                                              │
        │  Routing                                                     │
        │  ───────                                                     │
        │  route(spec)             → adapter for this spec             │
        │    ├── spec.runtime set? → exact match                       │
        │    └── spec.runtime None → capability-based selection        │
        │                                                              │
        │  Health                                                      │
        │  ──────                                                      │
        │  health_all()            → health of every registered adapter│
        │                                                              │
        │  Default                                                     │
        │  ───────                                                     │
        │  set_default(name)       → fallback when no spec.runtime set │
        │                                                              │
        └──────────────────────────────────────────────────────────────┘

    .. mermaid::

        flowchart TD
            SPEC[ContainerJobSpec] --> R{Router}
            R -->|spec.runtime='docker'| D[DockerAdapter]
            R -->|spec.runtime='k8s'| K[KubernetesAdapter]
            R -->|spec.runtime=None| DEF[Default adapter]
            R -->|not found| ERR[JobError NOT_FOUND]

Example:
    >>> from spine.execution.runtimes.router import RuntimeAdapterRouter
    >>> from spine.execution.runtimes._base import StubRuntimeAdapter
    >>>
    >>> router = RuntimeAdapterRouter()
    >>> router.register(StubRuntimeAdapter())
    >>> adapter = router.route(spec)  # uses spec.runtime or default

Manifesto:
    A single router selects the right runtime adapter for each
    spec based on declared requirements (GPU, memory, runtime
    label).  Adding a new backend is just registering an adapter.

Tags:
    spine-core, execution, runtimes, router, adapter-selection, strategy

Doc-Types:
    api-reference
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from spine.execution.runtimes._types import (
    ErrorCategory,
    JobError,
    RuntimeHealth,
)

if TYPE_CHECKING:
    from spine.execution.runtimes._types import (
        ContainerJobSpec,
        RuntimeAdapter,
    )

logger = logging.getLogger(__name__)


class RuntimeAdapterRouter:
    """Registry and router for runtime adapters.

    Manages a set of named adapters and picks the right one for each
    ``ContainerJobSpec``. Routing order:

    1. If ``spec.runtime`` is set → exact match by name
    2. If no ``spec.runtime`` → use the configured default adapter
    3. If no default → raise ``JobError(NOT_FOUND)``

    Thread-safe: registration is append-only in practice (adapters are
    registered at startup). Concurrent reads are safe for dict lookups.

    Example:
        >>> router = RuntimeAdapterRouter()
        >>> router.register(docker_adapter)
        >>> router.register(k8s_adapter)
        >>> router.set_default("docker")
        >>>
        >>> # Explicit runtime
        >>> spec = ContainerJobSpec(name="x", image="y", runtime="k8s")
        >>> adapter = router.route(spec)  # → k8s_adapter
        >>>
        >>> # Auto-route via default
        >>> spec2 = ContainerJobSpec(name="x", image="y")
        >>> adapter2 = router.route(spec2)  # → docker_adapter (default)
    """

    def __init__(self) -> None:
        self._adapters: dict[str, RuntimeAdapter] = {}
        self._default_name: str | None = None

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def register(self, adapter: RuntimeAdapter) -> None:
        """Register a runtime adapter.

        The adapter's ``runtime_name`` property is used as the registry key.
        If an adapter with the same name is already registered, it is
        replaced (with a warning).

        Args:
            adapter: The runtime adapter to register.

        Side effects:
            If this is the first adapter registered and no default is set,
            it automatically becomes the default.
        """
        name = adapter.runtime_name
        if name in self._adapters:
            logger.warning("Replacing existing adapter '%s'", name)
        self._adapters[name] = adapter
        logger.info("Registered runtime adapter '%s'", name)

        # Auto-set default if first adapter
        if self._default_name is None:
            self._default_name = name
            logger.info("Auto-set default runtime to '%s'", name)

    def unregister(self, name: str) -> bool:
        """Remove a runtime adapter by name.

        Args:
            name: Runtime name to remove.

        Returns:
            True if the adapter was found and removed, False otherwise.
        """
        if name not in self._adapters:
            return False
        del self._adapters[name]
        logger.info("Unregistered runtime adapter '%s'", name)
        if self._default_name == name:
            self._default_name = None
            logger.warning("Default runtime '%s' was unregistered", name)
        return True

    def get(self, name: str) -> RuntimeAdapter | None:
        """Get an adapter by exact name.

        Args:
            name: Runtime name (e.g., 'docker', 'k8s').

        Returns:
            The adapter, or None if not found.
        """
        return self._adapters.get(name)

    def set_default(self, name: str) -> None:
        """Set the default runtime adapter.

        Args:
            name: Runtime name to use as default.

        Raises:
            JobError: If no adapter with that name is registered.
        """
        if name not in self._adapters:
            raise JobError(
                category=ErrorCategory.NOT_FOUND,
                message=f"Cannot set default: no adapter registered as '{name}'",
                retryable=False,
            )
        self._default_name = name
        logger.info("Default runtime set to '%s'", name)

    def list_runtimes(self) -> list[str]:
        """List all registered runtime names.

        Returns:
            Sorted list of runtime names.
        """
        return sorted(self._adapters.keys())

    @property
    def default_name(self) -> str | None:
        """Current default runtime name, or None."""
        return self._default_name

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(self, spec: ContainerJobSpec) -> RuntimeAdapter:
        """Select the appropriate adapter for a spec.

        Routing logic:
        1. ``spec.runtime`` is set → exact match
        2. ``spec.runtime`` is None → default adapter
        3. No match → ``JobError(NOT_FOUND)``

        Args:
            spec: The container job specification.

        Returns:
            The selected runtime adapter.

        Raises:
            JobError: With ``category=NOT_FOUND`` if no adapter matches.
        """
        if spec.runtime:
            adapter = self._adapters.get(spec.runtime)
            if adapter is None:
                available = ", ".join(self.list_runtimes()) or "(none)"
                raise JobError(
                    category=ErrorCategory.NOT_FOUND,
                    message=(
                        f"No runtime adapter registered as '{spec.runtime}'. "
                        f"Available: {available}"
                    ),
                    retryable=False,
                )
            return adapter

        # No explicit runtime — use default
        if self._default_name and self._default_name in self._adapters:
            return self._adapters[self._default_name]

        # No default — fail
        if not self._adapters:
            raise JobError(
                category=ErrorCategory.NOT_FOUND,
                message="No runtime adapters registered",
                retryable=False,
            )

        raise JobError(
            category=ErrorCategory.NOT_FOUND,
            message=(
                "No default runtime set and spec.runtime is not specified. "
                f"Available runtimes: {', '.join(self.list_runtimes())}"
            ),
            retryable=False,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_all(self) -> dict[str, RuntimeHealth]:
        """Check health of all registered adapters.

        Returns:
            Dict mapping runtime name → ``RuntimeHealth``.
        """
        results: dict[str, RuntimeHealth] = {}
        for name, adapter in self._adapters.items():
            try:
                results[name] = await adapter.health()
            except Exception as exc:
                results[name] = RuntimeHealth(
                    healthy=False,
                    runtime=name,
                    message=f"Health check error: {exc}",
                )
        return results

    def __len__(self) -> int:
        """Number of registered adapters."""
        return len(self._adapters)

    def __contains__(self, name: str) -> bool:
        """Check if a runtime name is registered."""
        return name in self._adapters

    def __repr__(self) -> str:
        names = ", ".join(self.list_runtimes())
        default = f", default={self._default_name}" if self._default_name else ""
        return f"RuntimeAdapterRouter([{names}]{default})"
