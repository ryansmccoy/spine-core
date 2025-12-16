"""IBM DB2 database adapter.

Uses ``ibm_db_dbi`` — the DB-API 2.0 interface from the ``ibm-db``
package.  DB2 uses **qmark** (``?``) placeholder style natively.

Install the driver::

    pip install ibm-db
    # or:  pip install spine-core[db2]

This adapter is import-guarded: if ``ibm_db`` is not installed a clear
:class:`~spine.core.errors.ConfigError` is raised at ``connect()`` time
rather than at import time.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from spine.core.errors import ConfigError, DatabaseConnectionError
from spine.core.protocols import Connection

from .base import DatabaseAdapter
from .types import DatabaseConfig, DatabaseType


class DB2Adapter(DatabaseAdapter):
    """IBM DB2 database adapter.

    Uses ``ibm_db_dbi`` for DB-API 2.0 compliant access.
    Suitable for enterprise/mainframe deployments.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 50000,
        database: str = "",
        username: str | None = None,
        password: str | None = None,
        *,
        schema: str | None = None,
        **kwargs: Any,
    ):
        config = DatabaseConfig(
            db_type=DatabaseType.DB2,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            options={**(kwargs or {}), **({"schema": schema} if schema else {})},
        )
        super().__init__(config)
        self._conn: Any = None

    def connect(self) -> None:
        """Connect to DB2 database via ibm_db_dbi."""
        try:
            import ibm_db_dbi  # noqa: F401 — triggers ImportError if missing
        except ImportError:
            raise ConfigError(
                "ibm-db is required for DB2. Install with: pip install ibm-db"
            ) from None

        try:
            conn_str = (
                f"DATABASE={self._config.database};"
                f"HOSTNAME={self._config.host};"
                f"PORT={self._config.port};"
                f"PROTOCOL=TCPIP;"
                f"UID={self._config.username or ''};"
                f"PWD={self._config.password or ''};"
            )
            import ibm_db
            import ibm_db_dbi

            ibm_conn = ibm_db.connect(conn_str, "", "")
            self._conn = ibm_db_dbi.Connection(ibm_conn)

            # Set schema if provided
            schema = self._config.options.get("schema")
            if schema:
                self._conn.cursor().execute(f"SET SCHEMA {schema}")

            self._connected = True
        except Exception as e:
            raise DatabaseConnectionError(
                f"Failed to connect to DB2: {e}",
                cause=e,
            ) from e

    def disconnect(self) -> None:
        """Close DB2 connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._connected = False

    def get_connection(self) -> Connection:
        """Get the DB2 connection."""
        if not self._conn:
            self.connect()
        return self._conn

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

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute query and return results as dicts."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        if cursor.description is None:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


__all__ = [
    "DB2Adapter",
]
