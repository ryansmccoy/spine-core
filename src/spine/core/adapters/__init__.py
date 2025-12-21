"""Database adapters -- unified interface for 5 database backends.

Manifesto:
    Financial data operations must run identically on SQLite (dev), PostgreSQL
    (production), and sometimes DB2/Oracle (enterprise).  Without a common
    adapter interface, every operation embeds backend-specific SQL and connection
    logic -- making migrations between databases a multi-week project instead
    of a config change.

    Each adapter is **import-guarded**: the database driver is only required at
    ``connect()`` time, not at import time.  Install the corresponding extra::

        pip install spine-core[postgresql]   # psycopg2-binary
        pip install spine-core[db2]          # ibm-db
        pip install spine-core[mysql]        # mysql-connector-python
        pip install spine-core[oracle]       # oracledb

Architecture::

    DatabaseAdapter (base.py)        Abstract base with connect/execute/query
        |-- SQLiteAdapter            stdlib sqlite3 (always available)
        |-- PostgreSQLAdapter        psycopg2 (optional)
        |-- DB2Adapter               ibm_db_dbi (optional)
        |-- MySQLAdapter             mysql.connector (optional)
        |-- OracleAdapter            oracledb (optional)

    AdapterRegistry (registry.py)    Singleton: DatabaseType -> adapter class
    DatabaseConfig (types.py)        Pydantic config for connection parameters
    DatabaseType (types.py)          Enum of supported backends

Modules
-------
base            Abstract DatabaseAdapter base class
types           DatabaseType enum + DatabaseConfig model
registry        AdapterRegistry singleton + get_adapter() factory
sqlite          SQLite adapter (stdlib, always available)
postgresql      PostgreSQL adapter (requires psycopg2)
db2             IBM DB2 adapter (requires ibm-db)
mysql           MySQL / MariaDB adapter (requires mysql-connector-python)
oracle          Oracle adapter (requires oracledb)
database        Backward-compatible re-export shim

Guardrails:
    ❌ ``conn.execute("SELECT * FROM t WHERE id=" + user_input)``
    ✅ ``conn.execute("SELECT * FROM t WHERE id=?", [user_input])``
    ❌ Importing optional drivers at module scope
    ✅ Import-guarded at ``connect()`` time with clear ``ConfigError``
    ❌ ``adapter = PostgreSQLAdapter(...)`` directly
    ✅ ``adapter = get_adapter(DatabaseType.POSTGRESQL, config)``

Tags:
    spine-core, database, adapters, multi-backend, import-guarded,
    registry-pattern, postgresql, sqlite, db2, mysql, oracle

Doc-Types:
    package-overview, architecture-map, module-index
"""

from spine.core.dialect import Dialect, get_dialect
from spine.core.protocols import Connection

from .base import DatabaseAdapter
from .db2 import DB2Adapter
from .mysql import MySQLAdapter
from .oracle import OracleAdapter
from .postgresql import PostgreSQLAdapter
from .registry import AdapterRegistry, adapter_registry, get_adapter
from .sqlite import SQLiteAdapter
from .types import DatabaseConfig, DatabaseType

__all__ = [
    # Types
    "DatabaseType",
    "DatabaseConfig",
    # Protocols / Abstractions
    "Connection",
    "Dialect",
    "get_dialect",
    # Base class
    "DatabaseAdapter",
    # Implementations
    "SQLiteAdapter",
    "PostgreSQLAdapter",
    "DB2Adapter",
    "MySQLAdapter",
    "OracleAdapter",
    # Registry
    "AdapterRegistry",
    "adapter_registry",
    "get_adapter",
]
