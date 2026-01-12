"""
Database adapters package.

Provides unified interface for database operations across:
- SQLite (Basic tier)
- PostgreSQL (Intermediate/Advanced/Full)
- DB2 (Enterprise)
"""

from spine.core.adapters.database import (
    # Types
    DatabaseType,
    DatabaseConfig,
    # Protocols
    Connection,
    # Base class
    DatabaseAdapter,
    # Implementations
    SQLiteAdapter,
    PostgreSQLAdapter,
    # Registry
    AdapterRegistry,
    adapter_registry,
    get_adapter,
)

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
