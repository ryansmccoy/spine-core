"""Oracle database adapter.

Uses ``oracledb`` (python-oracledb) — the modern Oracle DB driver that
supersedes ``cx_Oracle``.  Oracle uses **numeric** (``:1``, ``:2``)
placeholder style.

Install the driver::

    pip install oracledb
    # or:  pip install spine-core[oracle]

This adapter is import-guarded: if ``oracledb`` is not installed a
clear :class:`~spine.core.errors.ConfigError` is raised at
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


class OracleAdapter(DatabaseAdapter):
    """Oracle database adapter.

    Uses ``oracledb`` with optional connection pooling.
    Suitable for enterprise and financial industry deployments.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1521,
        database: str = "",  # service name
        username: str | None = None,
        password: str | None = None,
        *,
        pool_size: int = 5,
        **kwargs: Any,
    ):
        config = DatabaseConfig(
            db_type=DatabaseType.ORACLE,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            pool_size=pool_size,
            options=kwargs or {},
        )
        super().__init__(config)
        self._pool: Any = None

    def connect(self) -> None:
        """Connect to Oracle database."""
        try:
            import oracledb  # noqa: F401
        except ImportError:
            raise ConfigError(
                "oracledb is required for Oracle. "
                "Install with: pip install oracledb"
            ) from None

        try:
            import oracledb

            dsn = oracledb.makedsn(
                self._config.host,
                self._config.port,
                service_name=self._config.database,
            )
            self._pool = oracledb.create_pool(
                user=self._config.username,
                password=self._config.password,
                dsn=dsn,
                min=1,
                max=self._config.pool_size,
                increment=1,
            )
            self._connected = True
        except Exception as e:
            raise DatabaseConnectionError(
                f"Failed to connect to Oracle: {e}",
                cause=e,
            ) from e

    def disconnect(self) -> None:
        """Close Oracle connection pool."""
        if self._pool:
            self._pool.close()
            self._pool = None
            self._connected = False

    def get_connection(self) -> Connection:
        """Get connection from pool."""
        if not self._pool:
            self.connect()
        return self._pool.acquire()

    def _return_connection(self, conn: Any) -> None:
        """Return connection to pool."""
        if self._pool:
            self._pool.release(conn)

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
            cursor = conn.cursor()
            cursor.execute(sql, params)
            if cursor.description is None:
                return []
            columns = [desc[0].lower() for desc in cursor.description]
            return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]
        finally:
            self._return_connection(conn)


__all__ = [
    "OracleAdapter",
]
