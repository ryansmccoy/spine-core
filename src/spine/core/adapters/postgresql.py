"""PostgreSQL database adapter."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from spine.core.errors import ConfigError, DatabaseConnectionError
from spine.core.protocols import Connection

from .base import DatabaseAdapter
from .types import DatabaseConfig, DatabaseType


class PostgreSQLAdapter(DatabaseAdapter):
    """
    PostgreSQL database adapter.

    Uses psycopg2 or asyncpg (wrapped with sync adapter).
    Suitable for production deployments.

    Note: Full implementation depends on application-level configuration.
    This is a stub that shows the interface.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "",
        username: str | None = None,
        password: str | None = None,
        *,
        pool_size: int = 5,
        ssl_mode: str = "prefer",
        **kwargs: Any,
    ):
        config = DatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            pool_size=pool_size,
            ssl_mode=ssl_mode,
            options=kwargs,
        )
        super().__init__(config)
        self._pool: Any = None

    def connect(self) -> None:
        """Connect to PostgreSQL database."""
        try:
            import psycopg2
            import psycopg2.pool
        except ImportError:
            raise ConfigError(
                "psycopg2 is required for PostgreSQL. Install with: pip install psycopg2-binary"
            ) from None

        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=self._config.pool_size,
                host=self._config.host,
                port=self._config.port,
                database=self._config.database,
                user=self._config.username,
                password=self._config.password,
                connect_timeout=self._config.connect_timeout,
            )
            self._connected = True
        except psycopg2.Error as e:
            raise DatabaseConnectionError(
                f"Failed to connect to PostgreSQL: {e}",
                cause=e,
            ) from e

    def disconnect(self) -> None:
        """Close PostgreSQL connection pool."""
        if self._pool:
            self._pool.closeall()
            self._pool = None
            self._connected = False

    def get_connection(self) -> Connection:
        """Get connection from pool."""
        if not self._pool:
            self.connect()
        return self._pool.getconn()

    def _return_connection(self, conn: Any) -> None:
        """Return connection to pool."""
        if self._pool:
            self._pool.putconn(conn)

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """Transaction context manager."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._return_connection(conn)


__all__ = [
    "PostgreSQLAdapter",
]
