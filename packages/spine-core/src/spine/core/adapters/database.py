"""
Database Adapter Protocol and implementations.

Provides a unified interface for database operations across:
- SQLite (Basic tier, development)
- PostgreSQL (Intermediate/Advanced/Full tiers)
- DB2 (Enterprise integration)

Design Principles:
- #3 Registry-Driven: Adapters registered by type
- #4 Protocol over Inheritance: Protocol defines interface
- #7 Explicit over Implicit: Clear dialect specification

All adapters use SYNCHRONOUS APIs to keep domain code simple.
Higher tiers wrap async drivers with sync adapters.

Usage:
    from spine.core.adapters.database import get_adapter, DatabaseType
    
    # Get adapter by type
    adapter = get_adapter(DatabaseType.SQLITE, path="data.db")
    
    # Or via registry
    from spine.core.adapters.database import adapter_registry
    adapter = adapter_registry.create("sqlite", path="data.db")
    
    # Use connection
    with adapter.transaction() as conn:
        conn.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from spine.core.errors import (
    ConfigError,
    DatabaseConnectionError,
    DatabaseError,
    QueryError,
)


class DatabaseType(str, Enum):
    """Supported database types."""
    
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    DB2 = "db2"
    MYSQL = "mysql"
    ORACLE = "oracle"


@dataclass
class DatabaseConfig:
    """
    Configuration for database connection.
    
    Different fields are used by different database types.
    """
    
    # Common
    db_type: DatabaseType = DatabaseType.SQLITE
    
    # SQLite
    path: str | None = None
    
    # PostgreSQL / MySQL / Oracle
    host: str = "localhost"
    port: int = 5432
    database: str = ""
    username: str | None = None
    password: str | None = None
    
    # Connection pool
    pool_size: int = 5
    pool_overflow: int = 10
    pool_timeout: int = 30
    
    # SSL
    ssl_mode: str = "prefer"  # disable, prefer, require, verify-ca, verify-full
    ssl_cert: str | None = None
    ssl_key: str | None = None
    ssl_ca: str | None = None
    
    # Options
    connect_timeout: int = 10
    query_timeout: int = 30
    readonly: bool = False
    
    # Extra options (driver-specific)
    options: dict[str, Any] = field(default_factory=dict)
    
    def to_connection_string(self) -> str:
        """Generate connection string for the database type."""
        match self.db_type:
            case DatabaseType.SQLITE:
                return self.path or ":memory:"
            case DatabaseType.POSTGRESQL:
                return (
                    f"postgresql://{self.username}:{self.password}"
                    f"@{self.host}:{self.port}/{self.database}"
                )
            case DatabaseType.MYSQL:
                return (
                    f"mysql://{self.username}:{self.password}"
                    f"@{self.host}:{self.port}/{self.database}"
                )
            case _:
                raise ConfigError(
                    f"Connection string not supported for: {self.db_type}"
                )


@runtime_checkable
class Connection(Protocol):
    """
    Minimal SYNCHRONOUS connection interface.
    
    This is a SYNC-ONLY protocol. Tiers with async drivers must provide
    sync adapters (e.g., run_sync() wrappers around asyncpg).
    """
    
    def execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute SQL statement with optional parameters."""
        ...
    
    def executemany(self, sql: str, params: list[tuple]) -> Any:
        """Execute SQL statement for multiple parameter sets."""
        ...
    
    def fetchone(self) -> Any:
        """Fetch one row from last query."""
        ...
    
    def fetchall(self) -> list:
        """Fetch all rows from last query."""
        ...
    
    def commit(self) -> None:
        """Commit current transaction."""
        ...
    
    def rollback(self) -> None:
        """Rollback current transaction."""
        ...


class DatabaseAdapter(ABC):
    """
    Abstract base class for database adapters.
    
    Provides common functionality and defines the interface
    that all adapters must implement.
    """
    
    def __init__(self, config: DatabaseConfig):
        self._config = config
        self._connected = False
    
    @property
    def db_type(self) -> DatabaseType:
        """Database type."""
        return self._config.db_type
    
    @property
    def is_connected(self) -> bool:
        """Whether adapter is connected."""
        return self._connected
    
    @abstractmethod
    def connect(self) -> None:
        """Establish connection to database."""
        ...
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to database."""
        ...
    
    @abstractmethod
    def get_connection(self) -> Connection:
        """Get a connection (may be from pool)."""
        ...
    
    @abstractmethod
    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """Context manager for a transaction."""
        ...
    
    def execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute SQL statement."""
        conn = self.get_connection()
        return conn.execute(sql, params)
    
    def executemany(self, sql: str, params: list[tuple]) -> Any:
        """Execute SQL for multiple parameter sets."""
        conn = self.get_connection()
        return conn.executemany(sql, params)
    
    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute query and return results as dicts."""
        conn = self.get_connection()
        cursor = conn.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def query_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Execute query and return single result."""
        results = self.query(sql, params)
        return results[0] if results else None
    
    def insert(
        self,
        table: str,
        data: dict[str, Any],
        returning: str | None = None,
    ) -> Any:
        """Insert a single row."""
        columns = list(data.keys())
        values = list(data.values())
        placeholders = self._get_placeholders(len(values))
        
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        if returning:
            sql += f" RETURNING {returning}"
        
        return self.execute(sql, tuple(values))
    
    def insert_many(self, table: str, rows: list[dict[str, Any]]) -> int:
        """Insert multiple rows."""
        if not rows:
            return 0
        
        columns = list(rows[0].keys())
        placeholders = self._get_placeholders(len(columns))
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        
        params = [tuple(row[col] for col in columns) for row in rows]
        self.executemany(sql, params)
        return len(rows)
    
    def _get_placeholders(self, count: int) -> str:
        """Get placeholder string for SQL parameters."""
        match self._config.db_type:
            case DatabaseType.SQLITE:
                return ", ".join("?" for _ in range(count))
            case DatabaseType.POSTGRESQL | DatabaseType.MYSQL:
                return ", ".join(f"${i+1}" for i in range(count))
            case _:
                return ", ".join("?" for _ in range(count))
    
    def __enter__(self) -> DatabaseAdapter:
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()


# =============================================================================
# SQLITE ADAPTER
# =============================================================================


class SQLiteAdapter(DatabaseAdapter):
    """
    SQLite database adapter.
    
    Uses the built-in sqlite3 module. Suitable for:
    - Development and testing
    - Basic tier deployments
    - Single-process applications
    """
    
    def __init__(
        self,
        path: str = ":memory:",
        *,
        readonly: bool = False,
        timeout: float = 5.0,
        **kwargs: Any,
    ):
        config = DatabaseConfig(
            db_type=DatabaseType.SQLITE,
            path=path,
            readonly=readonly,
            options=kwargs,
        )
        super().__init__(config)
        self._timeout = timeout
        self._conn: Any = None
    
    def connect(self) -> None:
        """Connect to SQLite database."""
        import sqlite3
        
        path = self._config.path or ":memory:"
        uri = path.startswith("file:") or "?" in path
        
        try:
            self._conn = sqlite3.connect(
                path,
                timeout=self._timeout,
                check_same_thread=False,
                uri=uri,
            )
            self._conn.row_factory = sqlite3.Row
            
            # Enable foreign keys
            self._conn.execute("PRAGMA foreign_keys = ON")
            
            if self._config.readonly:
                self._conn.execute("PRAGMA query_only = ON")
            
            self._connected = True
            
        except sqlite3.Error as e:
            raise DatabaseConnectionError(
                f"Failed to connect to SQLite: {e}",
                cause=e,
            )
    
    def disconnect(self) -> None:
        """Close SQLite connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._connected = False
    
    def get_connection(self) -> Connection:
        """Get the SQLite connection."""
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
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# POSTGRESQL ADAPTER (Stub for Intermediate Tier)
# =============================================================================


class PostgreSQLAdapter(DatabaseAdapter):
    """
    PostgreSQL database adapter.
    
    Uses psycopg2 or asyncpg (wrapped with sync adapter).
    Suitable for production deployments.
    
    Note: Full implementation provided by market-spine-intermediate.
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
                "psycopg2 is required for PostgreSQL. "
                "Install with: pip install psycopg2-binary"
            )
        
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
            )
    
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


# =============================================================================
# ADAPTER REGISTRY
# =============================================================================


class AdapterRegistry:
    """
    Registry for database adapter factories.
    
    Design Principle #3: Registry-Driven Discovery
    """
    
    def __init__(self):
        self._factories: dict[str, type[DatabaseAdapter]] = {}
        self._register_defaults()
    
    def _register_defaults(self) -> None:
        """Register default adapters."""
        self._factories["sqlite"] = SQLiteAdapter
        self._factories["postgresql"] = PostgreSQLAdapter
        self._factories["postgres"] = PostgreSQLAdapter  # Alias
    
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
