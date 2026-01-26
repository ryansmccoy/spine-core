# Database Adapters

> **Purpose:** Unified database interface supporting SQLite, PostgreSQL, and DB2.
> **Tier:** Basic (SQLite), Intermediate (PostgreSQL), Advanced (DB2)
> **Module:** `spine.core.storage`
> **Last Updated:** 2026-01-11

---

## Overview

Current state:
- SQLite-only via raw `sqlite3` connections
- No abstraction layer
- Dialect-specific SQL scattered in code
- No connection pooling

Target state:
- Unified `DatabaseAdapter` protocol
- Three implementations: SQLite, PostgreSQL, DB2
- Dialect-aware SQL generation
- Connection pooling for PostgreSQL/DB2
- Streaming support for large datasets

---

## Design Principles

1. **Protocol-Based** - Duck typing, not inheritance
2. **Dialect-Aware** - Adapters handle SQL differences
3. **Pooled** - Connection reuse for production
4. **Streaming** - Cursor-based iteration for large data
5. **Transactional** - Explicit transaction boundaries
6. **Testable** - Easy to mock and test

---

## Database Strategy

| Environment | Database | Use Case |
|-------------|----------|----------|
| Development | SQLite | Fast local dev, no setup |
| Unit Tests | SQLite (in-memory) | Isolated, fast tests |
| Integration Tests | PostgreSQL (Docker) | Production-like tests |
| Staging | PostgreSQL | Pre-production validation |
| Production | PostgreSQL | Standard deployment |
| Enterprise | DB2 | Legacy integration |

---

## Core Types

```python
# spine/core/storage/types.py
"""
Database adapter types.
"""

from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol
from contextlib import contextmanager


@dataclass(frozen=True)
class DatabaseConfig:
    """
    Database connection configuration.
    
    Supports multiple database types via connection string or params.
    """
    # Connection string approach (preferred)
    url: str | None = None
    
    # Param-based approach
    host: str | None = None
    port: int | None = None
    database: str | None = None
    user: str | None = None
    password: str | None = None
    
    # Pool settings (PostgreSQL/DB2)
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    
    # SQLite specific
    check_same_thread: bool = False
    
    # DB2 specific
    schema: str | None = None
    
    def __post_init__(self):
        if not self.url and not self.database:
            raise ValueError("Either url or database must be provided")
    
    @classmethod
    def sqlite(cls, path: str = ":memory:") -> "DatabaseConfig":
        """Create SQLite config."""
        return cls(url=f"sqlite:///{path}")
    
    @classmethod
    def postgres(
        cls,
        host: str = "localhost",
        port: int = 5432,
        database: str = "spine",
        user: str = "spine",
        password: str = "",
        **kwargs,
    ) -> "DatabaseConfig":
        """Create PostgreSQL config."""
        return cls(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            **kwargs,
        )
    
    @classmethod
    def db2(
        cls,
        host: str,
        port: int = 50000,
        database: str,
        user: str,
        password: str,
        schema: str | None = None,
        **kwargs,
    ) -> "DatabaseConfig":
        """Create DB2 config."""
        return cls(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            schema=schema,
            **kwargs,
        )
    
    @classmethod
    def from_env(cls, prefix: str = "SPINE_DB") -> "DatabaseConfig":
        """Create config from environment variables."""
        import os
        
        url = os.environ.get(f"{prefix}_URL")
        if url:
            return cls(url=url)
        
        return cls(
            host=os.environ.get(f"{prefix}_HOST", "localhost"),
            port=int(os.environ.get(f"{prefix}_PORT", "5432")),
            database=os.environ.get(f"{prefix}_NAME", "spine"),
            user=os.environ.get(f"{prefix}_USER", "spine"),
            password=os.environ.get(f"{prefix}_PASSWORD", ""),
            schema=os.environ.get(f"{prefix}_SCHEMA"),
        )


@dataclass
class QueryResult:
    """
    Result of a database query.
    
    Provides both eager (records) and lazy (stream) access.
    """
    columns: list[str]
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    row_count: int = 0
    
    @property
    def records(self) -> list[dict[str, Any]]:
        """Convert rows to dicts."""
        return [dict(zip(self.columns, row)) for row in self.rows]
    
    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate over records."""
        for row in self.rows:
            yield dict(zip(self.columns, row))
    
    def __len__(self) -> int:
        return len(self.rows)


# =============================================================================
# Database Adapter Protocol
# =============================================================================

class DatabaseAdapter(Protocol):
    """
    Protocol for database adapters.
    
    All adapters must implement this interface.
    """
    
    @property
    def dialect(self) -> str:
        """Database dialect: 'sqlite', 'postgresql', 'db2'."""
        ...
    
    def connect(self) -> None:
        """Establish connection(s) to database."""
        ...
    
    def close(self) -> None:
        """Close all connections."""
        ...
    
    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
    ) -> int:
        """
        Execute SQL statement.
        
        Returns number of affected rows.
        """
        ...
    
    def query(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
    ) -> QueryResult:
        """
        Execute query and return all results.
        
        For large result sets, prefer stream().
        """
        ...
    
    def stream(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
        batch_size: int = 1000,
    ) -> Iterator[dict[str, Any]]:
        """
        Execute query and stream results.
        
        Yields records one at a time to minimize memory.
        """
        ...
    
    def execute_many(
        self,
        sql: str,
        params_list: list[tuple[Any, ...] | dict[str, Any]],
    ) -> int:
        """
        Execute SQL with multiple parameter sets.
        
        Returns total affected rows.
        """
        ...
    
    @contextmanager
    def transaction(self):
        """
        Context manager for explicit transaction.
        
        Usage:
            with adapter.transaction():
                adapter.execute("INSERT ...")
                adapter.execute("UPDATE ...")
        """
        ...
    
    def table_exists(self, table_name: str) -> bool:
        """Check if table exists."""
        ...
    
    def get_columns(self, table_name: str) -> list[str]:
        """Get column names for table."""
        ...
```

---

## SQLite Adapter (Basic Tier)

```python
# spine/core/storage/sqlite.py
"""
SQLite database adapter.

Used for development, testing, and single-user deployments.
"""

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .types import DatabaseConfig, QueryResult


class SQLiteAdapter:
    """
    SQLite database adapter.
    
    Features:
    - In-memory or file-based
    - Row factory for dict access
    - Transaction support
    - Thread-safe (with check_same_thread=False)
    """
    
    dialect = "sqlite"
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._conn: sqlite3.Connection | None = None
        
        # Extract path from URL or use database param
        if config.url:
            self._path = config.url.replace("sqlite:///", "")
        else:
            self._path = config.database or ":memory:"
    
    def connect(self) -> None:
        """Open SQLite connection."""
        self._conn = sqlite3.connect(
            self._path,
            check_same_thread=self.config.check_same_thread,
        )
        self._conn.row_factory = sqlite3.Row
        
        # Enable foreign keys
        self._conn.execute("PRAGMA foreign_keys = ON")
    
    def close(self) -> None:
        """Close SQLite connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    @property
    def connection(self) -> sqlite3.Connection:
        """Get or create connection."""
        if self._conn is None:
            self.connect()
        return self._conn
    
    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
    ) -> int:
        """Execute SQL statement."""
        cursor = self.connection.execute(sql, params or ())
        self.connection.commit()
        return cursor.rowcount
    
    def query(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
    ) -> QueryResult:
        """Execute query and return all results."""
        cursor = self.connection.execute(sql, params or ())
        rows = cursor.fetchall()
        
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        
        return QueryResult(
            columns=columns,
            rows=[tuple(row) for row in rows],
            row_count=len(rows),
        )
    
    def stream(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
        batch_size: int = 1000,
    ) -> Iterator[dict[str, Any]]:
        """Stream query results."""
        cursor = self.connection.execute(sql, params or ())
        columns = [desc[0] for desc in cursor.description]
        
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield dict(zip(columns, row))
    
    def execute_many(
        self,
        sql: str,
        params_list: list[tuple[Any, ...] | dict[str, Any]],
    ) -> int:
        """Execute with multiple parameter sets."""
        cursor = self.connection.executemany(sql, params_list)
        self.connection.commit()
        return cursor.rowcount
    
    @contextmanager
    def transaction(self):
        """Explicit transaction context."""
        try:
            yield
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
    
    def table_exists(self, table_name: str) -> bool:
        """Check if table exists."""
        result = self.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return len(result) > 0
    
    def get_columns(self, table_name: str) -> list[str]:
        """Get column names."""
        result = self.query(f"PRAGMA table_info({table_name})")
        return [row["name"] for row in result]
```

---

## PostgreSQL Adapter (Intermediate Tier)

```python
# spine/core/storage/postgres.py
"""
PostgreSQL database adapter.

Used for staging, production, and multi-user deployments.
Requires: pip install psycopg[pool]
"""

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .types import DatabaseConfig, QueryResult


class PostgresAdapter:
    """
    PostgreSQL database adapter with connection pooling.
    
    Features:
    - Connection pooling via psycopg_pool
    - Named parameters (:name syntax)
    - Server-side cursors for streaming
    - COPY support for bulk loading
    """
    
    dialect = "postgresql"
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool: ConnectionPool | None = None
    
    def _build_conninfo(self) -> str:
        """Build connection string."""
        if self.config.url:
            return self.config.url.replace("postgresql://", "postgres://")
        
        return (
            f"host={self.config.host} "
            f"port={self.config.port} "
            f"dbname={self.config.database} "
            f"user={self.config.user} "
            f"password={self.config.password}"
        )
    
    def connect(self) -> None:
        """Initialize connection pool."""
        conninfo = self._build_conninfo()
        
        self._pool = ConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=self.config.pool_size,
            max_waiting=self.config.max_overflow,
            timeout=self.config.pool_timeout,
        )
    
    def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            self._pool.close()
            self._pool = None
    
    @property
    def pool(self) -> ConnectionPool:
        """Get or create pool."""
        if self._pool is None:
            self.connect()
        return self._pool
    
    @contextmanager
    def _get_connection(self):
        """Get connection from pool."""
        with self.pool.connection() as conn:
            yield conn
    
    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
    ) -> int:
        """Execute SQL statement."""
        # Convert ? placeholders to %s for psycopg
        sql = self._convert_placeholders(sql)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.rowcount
    
    def query(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
    ) -> QueryResult:
        """Execute query and return all results."""
        sql = self._convert_placeholders(sql)
        
        with self._get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                
                if cur.description is None:
                    return QueryResult(columns=[], rows=[], row_count=0)
                
                columns = [desc.name for desc in cur.description]
                rows = cur.fetchall()
                
                return QueryResult(
                    columns=columns,
                    rows=[tuple(row.values()) for row in rows],
                    row_count=len(rows),
                )
    
    def stream(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
        batch_size: int = 1000,
    ) -> Iterator[dict[str, Any]]:
        """Stream results using server-side cursor."""
        sql = self._convert_placeholders(sql)
        
        with self._get_connection() as conn:
            # Use named cursor for server-side execution
            with conn.cursor(name="stream_cursor", row_factory=dict_row) as cur:
                cur.itersize = batch_size
                cur.execute(sql, params)
                
                for row in cur:
                    yield dict(row)
    
    def execute_many(
        self,
        sql: str,
        params_list: list[tuple[Any, ...] | dict[str, Any]],
    ) -> int:
        """Execute with multiple parameter sets."""
        sql = self._convert_placeholders(sql)
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, params_list)
                return cur.rowcount
    
    @contextmanager
    def transaction(self):
        """Explicit transaction context."""
        with self._get_connection() as conn:
            try:
                yield
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def table_exists(self, table_name: str) -> bool:
        """Check if table exists."""
        result = self.query(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %(table)s
            )
            """,
            {"table": table_name},
        )
        return result.rows[0][0] if result.rows else False
    
    def get_columns(self, table_name: str) -> list[str]:
        """Get column names."""
        result = self.query(
            """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %(table)s
            ORDER BY ordinal_position
            """,
            {"table": table_name},
        )
        return [row["column_name"] for row in result]
    
    def _convert_placeholders(self, sql: str) -> str:
        """Convert ? placeholders to %s."""
        return sql.replace("?", "%s")
    
    # -------------------------------------------------------------------------
    # PostgreSQL-specific methods
    # -------------------------------------------------------------------------
    
    def copy_from(
        self,
        table: str,
        columns: list[str],
        data: Iterator[tuple],
    ) -> int:
        """Bulk load using COPY."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
                    for row in data:
                        copy.write_row(row)
                return cur.rowcount
```

---

## DB2 Adapter (Advanced Tier)

```python
# spine/core/storage/db2.py
"""
DB2 database adapter.

Used for enterprise integrations with legacy mainframe systems.
Requires: pip install ibm_db ibm_db_sa
"""

from contextlib import contextmanager
from typing import Any, Iterator
import logging

import ibm_db
import ibm_db_dbi

from .types import DatabaseConfig, QueryResult
from spine.core.errors import DependencyError


log = logging.getLogger(__name__)


class DB2Adapter:
    """
    IBM DB2 database adapter.
    
    Features:
    - Connection pooling via ibm_db pool
    - Schema-qualified table access
    - EBCDIC/ASCII encoding handling
    - Mainframe-specific SQL dialect
    
    DB2 SQL Differences:
    - FETCH FIRST n ROWS ONLY (vs LIMIT)
    - CURRENT DATE (vs NOW())
    - CONCAT() function (vs || operator)
    - Different date formatting
    """
    
    dialect = "db2"
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._conn = None
        self._schema = config.schema
    
    def _build_connection_string(self) -> str:
        """Build DB2 connection string."""
        return (
            f"DATABASE={self.config.database};"
            f"HOSTNAME={self.config.host};"
            f"PORT={self.config.port};"
            f"PROTOCOL=TCPIP;"
            f"UID={self.config.user};"
            f"PWD={self.config.password};"
        )
    
    def connect(self) -> None:
        """Establish DB2 connection."""
        try:
            conn_str = self._build_connection_string()
            self._conn = ibm_db.connect(conn_str, "", "")
            
            if self._schema:
                ibm_db.exec_immediate(
                    self._conn,
                    f"SET CURRENT SCHEMA = '{self._schema}'",
                )
                
            log.info(f"Connected to DB2: {self.config.database}")
            
        except Exception as e:
            raise DependencyError(
                f"Failed to connect to DB2: {e}",
                metadata={
                    "host": self.config.host,
                    "database": self.config.database,
                },
            )
    
    def close(self) -> None:
        """Close DB2 connection."""
        if self._conn:
            ibm_db.close(self._conn)
            self._conn = None
    
    @property
    def connection(self):
        """Get or create connection."""
        if self._conn is None:
            self.connect()
        return self._conn
    
    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
    ) -> int:
        """Execute SQL statement."""
        sql = self._adapt_sql(sql)
        
        if params:
            stmt = ibm_db.prepare(self.connection, sql)
            ibm_db.execute(stmt, params if isinstance(params, tuple) else tuple(params.values()))
            return ibm_db.num_rows(stmt)
        else:
            ibm_db.exec_immediate(self.connection, sql)
            return -1  # Row count not available for immediate exec
    
    def query(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
    ) -> QueryResult:
        """Execute query and return all results."""
        sql = self._adapt_sql(sql)
        
        if params:
            stmt = ibm_db.prepare(self.connection, sql)
            ibm_db.execute(stmt, params if isinstance(params, tuple) else tuple(params.values()))
        else:
            stmt = ibm_db.exec_immediate(self.connection, sql)
        
        # Get column names
        columns = []
        num_cols = ibm_db.num_fields(stmt)
        for i in range(num_cols):
            columns.append(ibm_db.field_name(stmt, i))
        
        # Fetch all rows
        rows = []
        row = ibm_db.fetch_tuple(stmt)
        while row:
            rows.append(row)
            row = ibm_db.fetch_tuple(stmt)
        
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
        )
    
    def stream(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
        batch_size: int = 1000,
    ) -> Iterator[dict[str, Any]]:
        """Stream query results."""
        sql = self._adapt_sql(sql)
        
        if params:
            stmt = ibm_db.prepare(self.connection, sql)
            ibm_db.execute(stmt, params if isinstance(params, tuple) else tuple(params.values()))
        else:
            stmt = ibm_db.exec_immediate(self.connection, sql)
        
        # Get column names
        columns = []
        num_cols = ibm_db.num_fields(stmt)
        for i in range(num_cols):
            columns.append(ibm_db.field_name(stmt, i))
        
        # Stream rows
        row = ibm_db.fetch_tuple(stmt)
        while row:
            yield dict(zip(columns, row))
            row = ibm_db.fetch_tuple(stmt)
    
    def execute_many(
        self,
        sql: str,
        params_list: list[tuple[Any, ...] | dict[str, Any]],
    ) -> int:
        """Execute with multiple parameter sets."""
        sql = self._adapt_sql(sql)
        stmt = ibm_db.prepare(self.connection, sql)
        
        total = 0
        for params in params_list:
            ibm_db.execute(stmt, params if isinstance(params, tuple) else tuple(params.values()))
            total += ibm_db.num_rows(stmt)
        
        return total
    
    @contextmanager
    def transaction(self):
        """Explicit transaction context."""
        try:
            yield
            ibm_db.commit(self.connection)
        except Exception:
            ibm_db.rollback(self.connection)
            raise
    
    def table_exists(self, table_name: str) -> bool:
        """Check if table exists."""
        schema = self._schema or self.config.user.upper()
        result = self.query(
            """
            SELECT 1 FROM SYSIBM.SYSTABLES 
            WHERE NAME = ? AND CREATOR = ?
            """,
            (table_name.upper(), schema),
        )
        return len(result) > 0
    
    def get_columns(self, table_name: str) -> list[str]:
        """Get column names."""
        schema = self._schema or self.config.user.upper()
        result = self.query(
            """
            SELECT NAME FROM SYSIBM.SYSCOLUMNS
            WHERE TBNAME = ? AND TBCREATOR = ?
            ORDER BY COLNO
            """,
            (table_name.upper(), schema),
        )
        return [row["NAME"] for row in result]
    
    def _adapt_sql(self, sql: str) -> str:
        """Adapt SQL for DB2 dialect."""
        # Convert LIMIT to FETCH FIRST
        import re
        
        limit_pattern = r"LIMIT\s+(\d+)"
        match = re.search(limit_pattern, sql, re.IGNORECASE)
        if match:
            n = match.group(1)
            sql = re.sub(limit_pattern, f"FETCH FIRST {n} ROWS ONLY", sql, flags=re.IGNORECASE)
        
        # Convert ? to parameter markers (already correct for DB2)
        return sql
```

---

## Adapter Registry

> **Design Principle: Registry-Driven (#3)**
> 
> Adding a new database adapter (e.g., MySQL, Oracle) should NOT require modifying 
> existing code. The registry pattern enables "Write Once" extensibility.

```python
# spine/core/storage/registry.py
"""
Database adapter registry.

Enables adding new adapters without modifying existing code.
"""

from typing import Callable, TypeVar
from .types import DatabaseConfig, DatabaseAdapter


T = TypeVar("T", bound=DatabaseAdapter)


class AdapterRegistry:
    """
    Registry for database adapters.
    
    Adapters register with URL prefixes. New adapters can be added
    by third parties without modifying this module.
    """
    
    def __init__(self):
        self._adapters: dict[str, type[DatabaseAdapter]] = {}
        self._default: str = "sqlite"
    
    def register(
        self,
        *prefixes: str,
    ) -> Callable[[type[T]], type[T]]:
        """
        Register adapter for URL prefix(es).
        
        Usage:
            @DATABASE_ADAPTERS.register("sqlite")
            class SQLiteAdapter:
                ...
                
            @DATABASE_ADAPTERS.register("postgres", "postgresql")
            class PostgresAdapter:
                ...
        """
        def decorator(cls: type[T]) -> type[T]:
            for prefix in prefixes:
                self._adapters[prefix] = cls
            return cls
        return decorator
    
    def get(self, config: DatabaseConfig) -> DatabaseAdapter:
        """
        Get adapter for configuration.
        
        Detects type from URL prefix or falls back to default.
        """
        if config.url:
            for prefix, adapter_cls in self._adapters.items():
                if config.url.startswith(prefix):
                    return adapter_cls(config)
        
        # Default adapter
        return self._adapters[self._default](config)
    
    def list(self) -> list[str]:
        """List registered adapter prefixes."""
        return list(self._adapters.keys())


# Global registry instance
DATABASE_ADAPTERS = AdapterRegistry()


# spine/core/storage/sqlite.py
@DATABASE_ADAPTERS.register("sqlite")
class SQLiteAdapter:
    """SQLite adapter - registered automatically."""
    dialect = "sqlite"
    # ... implementation


# spine/core/storage/postgres.py  
@DATABASE_ADAPTERS.register("postgres", "postgresql")
class PostgresAdapter:
    """PostgreSQL adapter - registered automatically."""
    dialect = "postgresql"
    # ... implementation


# spine/core/storage/db2.py
@DATABASE_ADAPTERS.register("db2", "ibm_db")
class DB2Adapter:
    """DB2 adapter - registered automatically."""
    dialect = "db2"
    # ... implementation
```

```python
# spine/core/storage/__init__.py
"""
Database storage adapters.

Provides unified interface for SQLite, PostgreSQL, and DB2.

Usage:
    from spine.core.storage import DATABASE_ADAPTERS, DatabaseConfig
    
    # SQLite (development)
    adapter = DATABASE_ADAPTERS.get(DatabaseConfig.sqlite("data/spine.db"))
    
    # PostgreSQL (production)
    adapter = DATABASE_ADAPTERS.get(DatabaseConfig.postgres(
        host="db.example.com",
        database="spine",
        user="app",
        password="secret",
    ))
    
    # DB2 (enterprise)
    adapter = DATABASE_ADAPTERS.get(DatabaseConfig.db2(
        host="mainframe.company.com",
        database="FINDATA",
        user="SPINEAPP",
        password="secret",
        schema="TRADING",
    ))
    
    # List available adapters
    print(DATABASE_ADAPTERS.list())  # ['sqlite', 'postgres', 'postgresql', 'db2', 'ibm_db']
    
Adding a New Adapter (Third-Party):
    # my_company/adapters/oracle.py
    from spine.core.storage import DATABASE_ADAPTERS, DatabaseConfig
    
    @DATABASE_ADAPTERS.register("oracle", "oracle+cx_oracle")
    class OracleAdapter:
        dialect = "oracle"
        
        def __init__(self, config: DatabaseConfig):
            ...
    
    # Now it just works:
    adapter = DATABASE_ADAPTERS.get(DatabaseConfig(url="oracle://..."))
"""

from .types import DatabaseConfig, QueryResult, DatabaseAdapter
from .registry import DATABASE_ADAPTERS
from .sqlite import SQLiteAdapter
from .postgres import PostgresAdapter
from .db2 import DB2Adapter

__all__ = [
    "DatabaseConfig",
    "QueryResult", 
    "DatabaseAdapter",
    "DATABASE_ADAPTERS",
    "SQLiteAdapter",
    "PostgresAdapter",
    "DB2Adapter",
]
```

---

## Dialect-Aware SQL

For queries that differ across databases:

```python
# spine/core/storage/dialect.py
"""
SQL dialect helpers.

Generates dialect-specific SQL for common operations.
"""

from typing import Any


class SQLDialect:
    """Generate SQL for specific database dialect."""
    
    def __init__(self, dialect: str):
        self.dialect = dialect
    
    def limit(self, n: int) -> str:
        """Generate LIMIT clause."""
        if self.dialect == "db2":
            return f"FETCH FIRST {n} ROWS ONLY"
        return f"LIMIT {n}"
    
    def current_timestamp(self) -> str:
        """Generate current timestamp expression."""
        if self.dialect == "db2":
            return "CURRENT TIMESTAMP"
        elif self.dialect == "postgresql":
            return "NOW()"
        else:
            return "datetime('now')"
    
    def concat(self, *columns: str) -> str:
        """Generate string concatenation."""
        if self.dialect == "db2":
            return f"CONCAT({', '.join(columns)})"
        elif self.dialect == "postgresql":
            return " || ".join(columns)
        else:
            return " || ".join(columns)
    
    def upsert(
        self,
        table: str,
        columns: list[str],
        conflict_columns: list[str],
        update_columns: list[str],
    ) -> str:
        """Generate UPSERT statement."""
        col_list = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        conflict = ", ".join(conflict_columns)
        
        if self.dialect == "postgresql":
            updates = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_columns])
            return f"""
                INSERT INTO {table} ({col_list})
                VALUES ({placeholders})
                ON CONFLICT ({conflict}) DO UPDATE SET {updates}
            """
        elif self.dialect == "sqlite":
            updates = ", ".join([f"{c} = excluded.{c}" for c in update_columns])
            return f"""
                INSERT INTO {table} ({col_list})
                VALUES ({placeholders})
                ON CONFLICT ({conflict}) DO UPDATE SET {updates}
            """
        elif self.dialect == "db2":
            # DB2 uses MERGE
            updates = ", ".join([f"T.{c} = S.{c}" for c in update_columns])
            src_cols = ", ".join([f"? AS {c}" for c in columns])
            join_cond = " AND ".join([f"T.{c} = S.{c}" for c in conflict_columns])
            return f"""
                MERGE INTO {table} AS T
                USING (SELECT {src_cols} FROM SYSIBM.SYSDUMMY1) AS S
                ON ({join_cond})
                WHEN MATCHED THEN UPDATE SET {updates}
                WHEN NOT MATCHED THEN INSERT ({col_list}) VALUES ({', '.join([f'S.{c}' for c in columns])})
            """
        
        raise ValueError(f"Unknown dialect: {self.dialect}")
    
    def boolean_literal(self, value: bool) -> str:
        """Generate boolean literal."""
        if self.dialect == "postgresql":
            return "TRUE" if value else "FALSE"
        elif self.dialect == "db2":
            return "1" if value else "0"
        else:  # SQLite
            return "1" if value else "0"
```

---

## Usage Examples

### Basic Usage

```python
from spine.core.storage import create_adapter, DatabaseConfig

# Development
config = DatabaseConfig.sqlite("data/spine.db")
adapter = create_adapter(config)
adapter.connect()

# Query
result = adapter.query("SELECT * FROM core_data_manifests WHERE domain = ?", ("finra",))
for row in result:
    print(row["manifest_id"], row["status"])

# Stream large dataset
for record in adapter.stream("SELECT * FROM fact_bond_trade_activity"):
    process_record(record)

adapter.close()
```

### With Context Manager

```python
# spine/core/storage/context.py
from contextlib import contextmanager
from .types import DatabaseConfig, DatabaseAdapter
from . import create_adapter


@contextmanager
def database_session(config: DatabaseConfig):
    """
    Context manager for database session.
    
    Usage:
        with database_session(config) as db:
            result = db.query("SELECT ...")
    """
    adapter = create_adapter(config)
    adapter.connect()
    try:
        yield adapter
    finally:
        adapter.close()
```

### In Pipelines

```python
# spine/domains/finra/otc_transparency/pipelines.py
from spine.core.storage import create_adapter, DatabaseConfig
from spine.core.storage.context import database_session
from spine.framework.pipelines import Pipeline


class IngestWeekPipeline(Pipeline):
    def run(self) -> PipelineResult:
        config = DatabaseConfig.from_env()
        
        with database_session(config) as db:
            # Check for existing data
            existing = db.query(
                "SELECT COUNT(*) as cnt FROM fact_bond_trade_activity WHERE week_ending = ?",
                (self.params["week_ending"],),
            )
            
            if existing.records[0]["cnt"] > 0:
                return PipelineResult.skipped("Data already exists")
            
            # Insert new data
            with db.transaction():
                db.execute_many(
                    """
                    INSERT INTO fact_bond_trade_activity 
                    (week_ending, tier, cusip, volume_total)
                    VALUES (?, ?, ?, ?)
                    """,
                    [(r["week"], r["tier"], r["cusip"], r["volume"]) for r in records],
                )
            
            return PipelineResult.completed(metrics={"inserted": len(records)})
```

---

## Testing

```python
# tests/core/storage/test_adapters.py
import pytest
from spine.core.storage import (
    create_adapter,
    DatabaseConfig,
    SQLiteAdapter,
    PostgresAdapter,
)


class TestSQLiteAdapter:
    def test_connect_in_memory(self):
        config = DatabaseConfig.sqlite(":memory:")
        adapter = SQLiteAdapter(config)
        adapter.connect()
        
        assert adapter.dialect == "sqlite"
        adapter.close()
    
    def test_execute_and_query(self):
        config = DatabaseConfig.sqlite(":memory:")
        adapter = SQLiteAdapter(config)
        adapter.connect()
        
        adapter.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        adapter.execute("INSERT INTO test VALUES (1, 'Alice')")
        adapter.execute("INSERT INTO test VALUES (2, 'Bob')")
        
        result = adapter.query("SELECT * FROM test ORDER BY id")
        
        assert len(result) == 2
        assert result.records[0]["name"] == "Alice"
        assert result.records[1]["name"] == "Bob"
    
    def test_stream(self):
        config = DatabaseConfig.sqlite(":memory:")
        adapter = SQLiteAdapter(config)
        adapter.connect()
        
        adapter.execute("CREATE TABLE test (id INTEGER)")
        for i in range(100):
            adapter.execute(f"INSERT INTO test VALUES ({i})")
        
        count = 0
        for row in adapter.stream("SELECT * FROM test", batch_size=10):
            count += 1
        
        assert count == 100
    
    def test_transaction_rollback(self):
        config = DatabaseConfig.sqlite(":memory:")
        adapter = SQLiteAdapter(config)
        adapter.connect()
        
        adapter.execute("CREATE TABLE test (id INTEGER)")
        adapter.execute("INSERT INTO test VALUES (1)")
        
        try:
            with adapter.transaction():
                adapter.execute("INSERT INTO test VALUES (2)")
                raise ValueError("Simulated error")
        except ValueError:
            pass
        
        result = adapter.query("SELECT COUNT(*) as cnt FROM test")
        assert result.records[0]["cnt"] == 1  # Rolled back


class TestAdapterFactory:
    def test_create_sqlite_from_url(self):
        config = DatabaseConfig(url="sqlite:///test.db")
        adapter = create_adapter(config)
        
        assert isinstance(adapter, SQLiteAdapter)
    
    def test_create_postgres_from_url(self):
        config = DatabaseConfig(url="postgresql://user:pass@localhost/db")
        adapter = create_adapter(config)
        
        assert isinstance(adapter, PostgresAdapter)
    
    def test_create_from_env(self, monkeypatch):
        monkeypatch.setenv("SPINE_DB_URL", "sqlite:///:memory:")
        
        config = DatabaseConfig.from_env()
        adapter = create_adapter(config)
        
        assert isinstance(adapter, SQLiteAdapter)
```

---

## Integration with Existing Code

### Migration Path

Current:
```python
import sqlite3

conn = sqlite3.connect("data/spine.db")
cursor = conn.execute("SELECT * FROM core_data_manifests")
rows = cursor.fetchall()
```

After:
```python
from spine.core.storage import create_adapter, DatabaseConfig

config = DatabaseConfig.from_env()  # Uses SPINE_DB_URL
adapter = create_adapter(config)
adapter.connect()

result = adapter.query("SELECT * FROM core_data_manifests")
for row in result:
    process(row)
```

---

## Dependencies

| Adapter | Package | Version |
|---------|---------|---------|
| SQLite | (built-in) | - |
| PostgreSQL | `psycopg[pool]` | >=3.0 |
| DB2 | `ibm_db` | >=3.0 |

---

## Next Steps

1. Build alerting framework: [05-ALERTING-FRAMEWORK.md](./05-ALERTING-FRAMEWORK.md)
2. Create scheduler service: [06-SCHEDULER-SERVICE.md](./06-SCHEDULER-SERVICE.md)
3. Document schema changes: [08-SCHEMA-CHANGES.md](./08-SCHEMA-CHANGES.md)
