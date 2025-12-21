"""
Database Adapter -- backward-compatible re-export shim.

The implementation has been split into focused modules:
- types.py       DatabaseType, DatabaseConfig
- base.py        DatabaseAdapter ABC
- sqlite.py      SQLiteAdapter
- postgresql.py  PostgreSQLAdapter
- registry.py    AdapterRegistry, adapter_registry, get_adapter

All public names remain importable from this module.

Tags:
    spine-core, database, shim, backward-compatibility

Doc-Types:
    api-reference
"""

from spine.core.adapters.base import DatabaseAdapter
from spine.core.adapters.postgresql import PostgreSQLAdapter
from spine.core.adapters.registry import AdapterRegistry, adapter_registry, get_adapter
from spine.core.adapters.sqlite import SQLiteAdapter
from spine.core.adapters.types import DatabaseConfig, DatabaseType
from spine.core.protocols import Connection

__all__ = [
    # Types
    "DatabaseType",
    "DatabaseConfig",
    # Protocols
    "Connection",
    # Base class
    "DatabaseAdapter",
    # Implementations
    "SQLiteAdapter",
    "PostgreSQLAdapter",
    # Registry
    "AdapterRegistry",
    "adapter_registry",
    "get_adapter",
]
