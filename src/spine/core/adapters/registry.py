"""Database adapter registry and factory.

Manifesto:
    Consumers should never hard-code adapter class names.  The registry
    maps ``DatabaseType`` strings to adapter classes and the ``get_adapter()``
    factory creates a configured instance from a config dict or URL.

Features:
    - ``AdapterRegistry`` singleton with pre-registered defaults
    - ``register()`` for custom / third-party adapters
    - ``get_adapter()`` factory: type + config → connected adapter

Tags:
    spine-core, database, registry, factory, singleton

Doc-Types:
    api-reference
"""

from __future__ import annotations

from typing import Any

from spine.core.errors import ConfigError

from .base import DatabaseAdapter
from .db2 import DB2Adapter
from .mysql import MySQLAdapter
from .oracle import OracleAdapter
from .postgresql import PostgreSQLAdapter
from .sqlite import SQLiteAdapter
from .types import DatabaseType


class AdapterRegistry:
    """
    Registry for database adapter factories.

    Design Principle #3: Registry-Driven Discovery

    Pre-registered adapters:
    - ``sqlite`` — :class:`SQLiteAdapter`
    - ``postgresql`` / ``postgres`` — :class:`PostgreSQLAdapter`
    - ``db2`` — :class:`DB2Adapter`
    - ``mysql`` — :class:`MySQLAdapter`
    - ``oracle`` — :class:`OracleAdapter`
    """

    def __init__(self):
        self._factories: dict[str, type[DatabaseAdapter]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default adapters."""
        self._factories["sqlite"] = SQLiteAdapter
        self._factories["postgresql"] = PostgreSQLAdapter
        self._factories["postgres"] = PostgreSQLAdapter  # Alias
        self._factories["db2"] = DB2Adapter
        self._factories["mysql"] = MySQLAdapter
        self._factories["oracle"] = OracleAdapter

    def register(self, name: str, adapter_class: type[DatabaseAdapter]) -> None:
        """Register an adapter factory."""
        self._factories[name.lower()] = adapter_class

    def create(self, name: str, **kwargs: Any) -> DatabaseAdapter:
        """Create an adapter by name."""
        name = name.lower()
        if name not in self._factories:
            raise ConfigError(f"Unknown database adapter: {name}")
        return self._factories[name](**kwargs)

    def list_adapters(self) -> list[str]:
        """List registered adapter names."""
        return sorted(self._factories.keys())


# Global registry
adapter_registry = AdapterRegistry()


def get_adapter(
    db_type: DatabaseType | str,
    **kwargs: Any,
) -> DatabaseAdapter:
    """
    Get a database adapter by type.

    Usage:
        adapter = get_adapter(DatabaseType.SQLITE, path="data.db")
        adapter = get_adapter("postgresql", host="localhost", database="spine")
    """
    if isinstance(db_type, DatabaseType):
        name = db_type.value
    else:
        name = db_type

    return adapter_registry.create(name, **kwargs)


__all__ = [
    "AdapterRegistry",
    "adapter_registry",
    "get_adapter",
]
