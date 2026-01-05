"""
Database connection provider for framework components.

This module provides a pluggable connection mechanism that allows
different tiers to inject their own database implementations:
- Basic: sqlite3 connection
- Intermediate/Advanced: asyncpg via sync adapter

Usage in tier-specific code (e.g., market_spine/db.py):
    from spine.framework.db import set_connection_provider
    set_connection_provider(get_sqlite_connection)

Usage in domain pipelines:
    from spine.framework.db import get_connection
    conn = get_connection()
"""

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Connection(Protocol):
    """Minimal database connection protocol."""

    def execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute SQL statement."""
        ...

    def executemany(self, sql: str, params: list[tuple]) -> Any:
        """Execute SQL for multiple parameter sets."""
        ...

    def commit(self) -> None:
        """Commit transaction."""
        ...


# Type for connection provider function
ConnectionProvider = Callable[[], Connection]

# Global connection provider (set by tier at startup)
_connection_provider: ConnectionProvider | None = None


def set_connection_provider(provider: ConnectionProvider) -> None:
    """
    Set the connection provider function.

    Called once at application startup by the tier-specific code.

    Args:
        provider: Function that returns a database connection
    """
    global _connection_provider
    _connection_provider = provider


def get_connection() -> Connection:
    """
    Get a database connection from the configured provider.

    Raises:
        RuntimeError: If no connection provider has been set
    """
    if _connection_provider is None:
        raise RuntimeError(
            "No connection provider configured. "
            "Call set_connection_provider() at application startup."
        )
    return _connection_provider()


def clear_connection_provider() -> None:
    """Clear the connection provider (for testing)."""
    global _connection_provider
    _connection_provider = None
