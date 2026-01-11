"""Database connection pool management."""

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg_pool import ConnectionPool

from market_spine.core.settings import get_settings

_pool: ConnectionPool | None = None


def init_pool() -> ConnectionPool:
    """Initialize the connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    settings = get_settings()
    _pool = ConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        open=True,
    )
    return _pool


def get_pool() -> ConnectionPool:
    """Get the connection pool, initializing if needed."""
    global _pool
    if _pool is None:
        return init_pool()
    return _pool


def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Get a connection from the pool."""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def reset_pool() -> None:
    """Reset the pool (for testing)."""
    global _pool
    if _pool is not None:
        _pool.close()
    _pool = None
