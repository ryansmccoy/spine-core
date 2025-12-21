"""Handler Registry — injectable name → handler lookup.

Manifesto:
The EventDispatcher needs to resolve ``"task:send_email"`` to a
callable handler.  The registry decouples registration (at import
time or startup) from resolution (at dispatch time), and supports
both a global singleton and injectable instances for testing.

ARCHITECTURE
────────────
::

    HandlerRegistry
      ├── .register(kind, name, handler)  ─ store handler
      ├── .get(kind, name)                ─ lookup by key
      ├── .list_handlers()                ─ all registered keys
      └── .has(kind, name)                ─ existence check

    Convenience decorators (use global registry):
      register_task(name)        → registers as "task:{name}"
      register_operation(name)    → registers as "operation:{name}"
      register_workflow(name)    → registers as "workflow:{name}"
      register_step(name)        → registers as "step:{name}"

    get_default_registry()     ─ module-level singleton
    reset_default_registry()   ─ clear for testing

BEST PRACTICES
──────────────
- Use ``register_task`` / ``register_operation`` decorators for
  production code; pass explicit ``HandlerRegistry`` in tests.
- Call ``reset_default_registry()`` in test fixtures.

Related modules:
    dispatcher.py — EventDispatcher uses the registry
    handlers.py   — built-in example handlers
    spec.py       — WorkSpec references handler by name

Tags:
    spine-core, execution, registry, handler-registry, lookup

Doc-Types:
    api-reference
"""

from collections.abc import Callable
from typing import Any


class HandlerRegistry:
    """Injectable handler registry.

    Can be passed to Dispatcher for:
    - Testing (isolated registries per test)
    - Multi-tenant (per-tenant handlers)
    - Plugins (dynamic loading)

    Example:
        >>> registry = HandlerRegistry()
        >>>
        >>> @register_task("send_email", registry=registry)
        >>> async def send_email(params):
        ...     return {"sent": True}
        >>>
        >>> handler = registry.get("task", "send_email")
        >>> result = await handler({"to": "user@example.com"})
    """

    def __init__(self):
        self._handlers: dict[str, Callable] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        kind: str,
        name: str,
        handler: Callable,
        description: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Register a handler.

        Args:
            kind: Work kind (task, operation, workflow, step)
            name: Handler name
            handler: Callable to execute
            description: Optional description for documentation
            tags: Optional tags for filtering/categorization
        """
        key = f"{kind}:{name}"
        self._handlers[key] = handler
        self._metadata[key] = {
            "kind": kind,
            "name": name,
            "description": description,
            "tags": tags or {},
        }

    def get(self, kind: str, name: str) -> Callable:
        """Get a handler.

        Args:
            kind: Work kind
            name: Handler name

        Returns:
            Handler callable

        Raises:
            ValueError: If handler not found
        """
        key = f"{kind}:{name}"
        if key not in self._handlers:
            available = [k for k in self._handlers.keys() if k.startswith(f"{kind}:")]
            raise ValueError(f"No handler registered for {key}. Available {kind} handlers: {available or 'none'}")
        return self._handlers[key]

    def has(self, kind: str, name: str) -> bool:
        """Check if handler exists."""
        key = f"{kind}:{name}"
        return key in self._handlers

    def get_metadata(self, kind: str, name: str) -> dict[str, Any] | None:
        """Get handler metadata (description, tags, etc.)."""
        key = f"{kind}:{name}"
        return self._metadata.get(key)

    def list_handlers(self, kind: str | None = None) -> list[tuple[str, str]]:
        """List all registered handlers.

        Args:
            kind: Optional filter by kind

        Returns:
            List of (kind, name) tuples
        """
        handlers = []
        for key in self._handlers.keys():
            k, n = key.split(":", 1)
            if kind is None or k == kind:
                handlers.append((k, n))
        return sorted(handlers)

    def list_with_metadata(self, kind: str | None = None) -> list[dict[str, Any]]:
        """List handlers with their metadata.

        Useful for building documentation or admin UIs.
        """
        result = []
        for _key, metadata in self._metadata.items():
            if kind is None or metadata["kind"] == kind:
                result.append(metadata.copy())
        return sorted(result, key=lambda x: (x["kind"], x["name"]))

    def unregister(self, kind: str, name: str) -> bool:
        """Unregister a handler.

        Args:
            kind: Work kind
            name: Handler name

        Returns:
            True if handler was removed, False if not found
        """
        key = f"{kind}:{name}"
        if key in self._handlers:
            del self._handlers[key]
            del self._metadata[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all handlers (for testing)."""
        self._handlers.clear()
        self._metadata.clear()

    def to_executor_handlers(self) -> dict[str, Callable]:
        """Convert to executor-compatible handler dict.

        Returns dict mapping "kind:name" -> handler, suitable for
        passing to MemoryExecutor or LocalExecutor.
        """
        return self._handlers.copy()


# === GLOBAL DEFAULT REGISTRY ===

_default_registry: HandlerRegistry | None = None


def get_default_registry() -> HandlerRegistry:
    """Get the global default registry.

    Creates it lazily on first access.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = HandlerRegistry()
    return _default_registry


def reset_default_registry() -> None:
    """Reset the global registry (for testing)."""
    global _default_registry
    _default_registry = None


# === DECORATOR API ===


def register_handler(
    kind: str,
    name: str,
    registry: HandlerRegistry | None = None,
    description: str | None = None,
    tags: dict[str, str] | None = None,
):
    """Decorator to register a handler.

    Args:
        kind: Work kind (task, operation, workflow, step)
        name: Handler name
        registry: Optional registry (uses global if None)
        description: Optional description
        tags: Optional tags

    Example:
        >>> @register_handler("task", "send_email")
        >>> async def send_email(params):
        ...     # Send email
        ...     return {"sent": True}
    """
    target = registry or get_default_registry()

    def decorator(func: Callable) -> Callable:
        target.register(
            kind,
            name,
            func,
            description=description or func.__doc__,
            tags=tags,
        )
        return func

    return decorator


# === CONVENIENCE SHORTCUTS ===


def register_task(
    name: str,
    registry: HandlerRegistry | None = None,
    description: str | None = None,
    tags: dict[str, str] | None = None,
):
    """Convenience: register a task handler.

    Example:
        >>> @register_task("send_email")
        >>> async def send_email(params):
        ...     return {"sent": True}
    """
    return register_handler("task", name, registry, description, tags)


def register_operation(
    name: str,
    registry: HandlerRegistry | None = None,
    description: str | None = None,
    tags: dict[str, str] | None = None,
):
    """Convenience: register a operation handler.

    Example:
        >>> @register_operation("ingest_otc")
        >>> async def ingest_otc(params):
        ...     return {"rows": 1000}
    """
    return register_handler("operation", name, registry, description, tags)


def register_workflow(
    name: str,
    registry: HandlerRegistry | None = None,
    description: str | None = None,
    tags: dict[str, str] | None = None,
):
    """Convenience: register a workflow handler.

    Example:
        >>> @register_workflow("daily_ingest")
        >>> async def daily_ingest(params):
        ...     # Run workflow steps
        ...     return {"status": "completed"}
    """
    return register_handler("workflow", name, registry, description, tags)


def register_step(
    name: str,
    registry: HandlerRegistry | None = None,
    description: str | None = None,
    tags: dict[str, str] | None = None,
):
    """Convenience: register a workflow step handler.

    Example:
        >>> @register_step("validate")
        >>> async def validate_step(params):
        ...     return {"valid": True}
    """
    return register_handler("step", name, registry, description, tags)
