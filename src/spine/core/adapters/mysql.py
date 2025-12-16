"""MySQL database adapter.

Uses ``mysql.connector`` from the ``mysql-connector-python`` package.
MySQL uses **format** (``%s``) placeholder style.

Install the driver::

    pip install mysql-connector-python
    # or:  pip install spine-core[mysql]

This adapter is import-guarded: if ``mysql.connector`` is not installed
a clear :class:`~spine.core.errors.ConfigError` is raised at
``connect()`` time.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from spine.core.errors import ConfigError, DatabaseConnectionError
from spine.core.protocols import Connection

from .base import DatabaseAdapter
from .types import DatabaseConfig, DatabaseType


class MySQLAdapter(DatabaseAdapter):
    """MySQL / MariaDB database adapter.

    Uses ``mysql.connector`` with optional connection pooling.
    Suitable for web-scale and cloud deployments.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        database: str = "",
        username: str | None = None,
        password: str | None = None,
        *,
        pool_size: int = 5,
        charset: str = "utf8mb4",
        **kwargs: Any,
    ):
        config = DatabaseConfig(
            db_type=DatabaseType.MYSQL,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            pool_size=pool_size,
            options={**(kwargs or {}), "charset": charset},
        )
        super().__init__(config)
        self._pool: Any = None
        self._conn: Any = None

    def connect(self) -> None:
        """Connect to MySQL database."""
        try:
            import mysql.connector  # noqa: F401
            from mysql.connector import pooling
        except ImportError:
            raise ConfigError(
                "mysql-connector-python is required for MySQL. "
                "Install with: pip install mysql-connector-python"
            ) from None

        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name="spine_mysql_pool",
                pool_size=self._config.pool_size,
                host=self._config.host,
                port=self._config.port,
                database=self._config.database,
                user=self._config.username,
                password=self._config.password,
                charset=self._config.options.get("charset", "utf8mb4"),
                connect_timeout=self._config.connect_timeout,
                autocommit=False,
            )
            self._connected = True
        except Exception as e:
            raise DatabaseConnectionError(
                f"Failed to connect to MySQL: {e}",
                cause=e,
            ) from e

    def disconnect(self) -> None:
        """Close MySQL connection pool."""
        # mysql.connector pool doesn't have a closeall(); close active conn
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        self._pool = None
        self._connected = False

    def get_connection(self) -> Connection:
        """Get connection from pool."""
        if not self._pool:
            self.connect()
        self._conn = self._pool.get_connection()
        return self._conn

    def _return_connection(self, conn: Any) -> None:
        """Return connection to pool."""
        try:
            conn.close()  # mysql.connector returns to pool on close
        except Exception:
            pass

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

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute query and return results as dicts."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params)
            return cursor.fetchall()
        finally:
            self._return_connection(conn)


__all__ = [
    "MySQLAdapter",
]
