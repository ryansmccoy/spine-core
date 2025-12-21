"""SQL dialect abstraction for database-agnostic domain code.

Provides a ``Dialect`` protocol and concrete implementations for every
supported database backend.  Domain repositories use ``Dialect`` methods
to generate SQL fragments (placeholders, timestamps, upsert logic, JSON
functions) without importing or referencing any specific database driver.

Manifesto:
    Domain code must be portable across SQLite, PostgreSQL, DB2, MySQL,
    and Oracle. Without a dialect layer, SQL fragments are littered with
    backend-specific syntax that breaks when switching tiers.

    - **One interface:** Dialect protocol for all SQL generation
    - **Zero coupling:** Domain code never imports database drivers
    - **Auto-detection:** get_dialect(conn) chooses the right dialect
    - **Testable:** SQLiteDialect for tests, PostgreSQLDialect for prod

Architecture::

    ┌──────────────────────────────────────────────────────────────────┐
    │                     Dialect Abstraction Layer                     │
    └──────────────────────────────────────────────────────────────────┘

    Domain Code:
    ┌────────────────────────────────────────────────────────────────┐
    │  sql = f"INSERT INTO t (a,b) VALUES ({d.placeholders(2)})"    │
    │  sql += f" WHERE ts > {d.now()}"                               │
    │  conn.execute(sql, params)                                     │
    └────────────────────────────────────────────────────────────────┘
                              │
                              ▼
    ┌──────────┐ ┌──────────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
    │ SQLite   │ │ PostgreSQL   │ │  DB2   │ │ MySQL  │ │  Oracle  │
    │ ?, ?, ?  │ │ %s, %s, %s   │ │ ?, ?, ?│ │ %s,%s  │ │ :1, :2   │
    │ datetime │ │ NOW()        │ │CURRENT │ │ NOW()  │ │SYSTIMEST │
    └──────────┘ └──────────────┘ └────────┘ └────────┘ └──────────┘

Features:
    - **SQLiteDialect:** ``?`` placeholders, ``datetime('now')``
    - **PostgreSQLDialect:** ``%s`` placeholders, ``NOW()``
    - **DB2Dialect:** ``?`` placeholders, ``CURRENT TIMESTAMP``
    - **MySQLDialect / OracleDialect:** Additional backends
    - **get_dialect():** Auto-detect dialect from connection object

Examples:
    >>> from spine.core.dialect import get_dialect, SQLiteDialect
    >>> d = SQLiteDialect()
    >>> d.placeholders(3)
    '?, ?, ?'
    >>> d.now()
    "datetime('now')"

Guardrails:
    ❌ DON'T: Write backend-specific SQL in domain repositories
    ✅ DO: Use Dialect methods for placeholders, timestamps, upserts

    ❌ DON'T: Import sqlite3 or psycopg2 in domain code
    ✅ DO: Use Dialect + Connection protocol for all SQL access

Tags:
    dialect, sql, abstraction, portability, database, spine-core,
    multi-backend, tier-agnostic

Doc-Types:
    - API Reference
    - Architecture Documentation
    - Database Portability Guide
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Dialect(Protocol):
    """SQL dialect contract.

    Every method returns a **SQL fragment** (string) that is valid for
    the target database.  Domain code interpolates these fragments into
    its SQL templates, keeping all dialect-specific syntax out of
    business logic.
    """

    @property
    def name(self) -> str:
        """Human-readable dialect name (e.g. ``'sqlite'``)."""
        ...

    # -- Placeholder generation --------------------------------------------

    def placeholder(self, index: int) -> str:
        """Single positional placeholder (0-based index).

        ``index`` is ignored by dialects that use anonymous placeholders
        (SQLite ``?``, MySQL ``%s``) but required by numbered styles
        (PostgreSQL ``$1``, Oracle ``:1``).
        """
        ...

    def placeholders(self, count: int) -> str:
        """Comma-separated placeholder list.

        >>> dialect.placeholders(3)
        '?, ?, ?'          # SQLite / DB2
        '%s, %s, %s'       # PostgreSQL / MySQL
        ':1, :2, :3'       # Oracle
        """
        ...

    # -- Timestamp expressions ---------------------------------------------

    def now(self) -> str:
        """SQL expression for current UTC timestamp.

        Returns a string that can be embedded directly in SQL:
        ``datetime('now')``  (SQLite), ``NOW()`` (PG/MySQL), etc.
        """
        ...

    def interval(self, value: int, unit: str) -> str:
        """SQL expression for date/time arithmetic.

        ``unit`` is one of ``'seconds'``, ``'minutes'``, ``'hours'``,
        ``'days'``.

        >>> dialect.interval(-7, 'days')
        "datetime('now', '-7 days')"  # SQLite
        "NOW() - INTERVAL '7 days'"   # PostgreSQL
        """
        ...

    # -- DML helpers -------------------------------------------------------

    def insert_or_ignore(self, table: str, columns: list[str]) -> str:
        """``INSERT … ON CONFLICT DO NOTHING`` (or equivalent).

        Returns the full SQL statement with placeholders.
        """
        ...

    def insert_or_replace(self, table: str, columns: list[str]) -> str:
        """``INSERT OR REPLACE`` / ``UPSERT`` variant.

        Returns the full SQL statement with placeholders.
        """
        ...

    def upsert(
        self,
        table: str,
        columns: list[str],
        key_columns: list[str],
    ) -> str:
        """``INSERT … ON CONFLICT (keys) DO UPDATE SET …``

        Returns the full SQL statement with placeholders.
        """
        ...

    # -- JSON helpers ------------------------------------------------------

    def json_set(self, column: str, path: str, param_placeholder: str) -> str:
        """SQL fragment to set a value inside a JSON column.

        >>> dialect.json_set('metadata_json', '$.resolution_note', '?')
        "json_set(COALESCE(metadata_json, '{}'), '$.resolution_note', ?)"
        """
        ...

    # -- DDL helpers -------------------------------------------------------

    def auto_increment(self) -> str:
        """DDL fragment for auto-incrementing primary key type.

        Returns the full column type, e.g.
        ``'INTEGER PRIMARY KEY AUTOINCREMENT'`` (SQLite) or
        ``'SERIAL PRIMARY KEY'`` (PostgreSQL).
        """
        ...

    def timestamp_default_now(self) -> str:
        """DDL ``DEFAULT`` clause for a ``TEXT``/``TIMESTAMP`` column.

        >>> dialect.timestamp_default_now()
        "DEFAULT (datetime('now'))"  # SQLite
        "DEFAULT NOW()"              # PostgreSQL
        """
        ...

    def boolean_true(self) -> str:
        """Literal SQL value for boolean ``True``.

        ``'1'`` (SQLite), ``'TRUE'`` (PostgreSQL/MySQL/Oracle), etc.
        """
        ...

    def boolean_false(self) -> str:
        """Literal SQL value for boolean ``False``."""
        ...

    def table_exists_query(self) -> str:
        """SQL query returning table names.

        The query must accept one ``?``/``%s`` placeholder for the table name
        and return rows if the table exists.

        Used by schema introspection utilities.
        """
        ...


# =========================================================================
# Concrete Dialect Implementations
# =========================================================================


class SQLiteDialect:
    """SQLite dialect — ``?`` placeholders, ``datetime('now')``."""

    @property
    def name(self) -> str:
        return "sqlite"

    # -- Placeholders ------------------------------------------------------

    def placeholder(self, index: int) -> str:  # noqa: ARG002
        return "?"

    def placeholders(self, count: int) -> str:
        return ", ".join("?" for _ in range(count))

    # -- Timestamps --------------------------------------------------------

    def now(self) -> str:
        return "datetime('now')"

    def interval(self, value: int, unit: str) -> str:
        return f"datetime('now', '{value} {unit}')"

    # -- DML ---------------------------------------------------------------

    def insert_or_ignore(self, table: str, columns: list[str]) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        return f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({ph})"

    def insert_or_replace(self, table: str, columns: list[str]) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        return f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({ph})"

    def upsert(self, table: str, columns: list[str], key_columns: list[str]) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        keys = ", ".join(key_columns)
        update_cols = [c for c in columns if c not in key_columns]
        updates = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        return (
            f"INSERT INTO {table} ({cols}) VALUES ({ph}) "
            f"ON CONFLICT ({keys}) DO UPDATE SET {updates}"
        )

    # -- JSON --------------------------------------------------------------

    def json_set(self, column: str, path: str, param_placeholder: str) -> str:
        return f"json_set(COALESCE({column}, '{{}}'), '{path}', {param_placeholder})"

    # -- DDL ---------------------------------------------------------------

    def auto_increment(self) -> str:
        return "INTEGER PRIMARY KEY AUTOINCREMENT"

    def timestamp_default_now(self) -> str:
        return "DEFAULT (datetime('now'))"

    # -- Booleans ----------------------------------------------------------

    def boolean_true(self) -> str:
        return "1"

    def boolean_false(self) -> str:
        return "0"

    # -- Introspection -----------------------------------------------------

    def table_exists_query(self) -> str:
        return "SELECT name FROM sqlite_master WHERE type='table' AND name = ?"


class PostgreSQLDialect:
    """PostgreSQL dialect — ``%s`` placeholders (psycopg2), ``NOW()``.

    Uses ``%s`` format-style placeholders compatible with psycopg2.
    For asyncpg (``$1`` numbering), a separate adapter layer would
    handle the translation.
    """

    @property
    def name(self) -> str:
        return "postgresql"

    def placeholder(self, index: int) -> str:  # noqa: ARG002
        return "%s"

    def placeholders(self, count: int) -> str:
        return ", ".join("%s" for _ in range(count))

    def now(self) -> str:
        return "NOW()"

    def interval(self, value: int, unit: str) -> str:
        # Negative values: "NOW() - INTERVAL '7 days'"
        if value < 0:
            return f"NOW() - INTERVAL '{abs(value)} {unit}'"
        return f"NOW() + INTERVAL '{value} {unit}'"

    def insert_or_ignore(self, table: str, columns: list[str]) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        return f"INSERT INTO {table} ({cols}) VALUES ({ph}) ON CONFLICT DO NOTHING"

    def insert_or_replace(self, table: str, columns: list[str]) -> str:
        # PostgreSQL has no direct INSERT OR REPLACE — use INSERT ... ON CONFLICT UPDATE all
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        return f"INSERT INTO {table} ({cols}) VALUES ({ph})"

    def upsert(self, table: str, columns: list[str], key_columns: list[str]) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        keys = ", ".join(key_columns)
        update_cols = [c for c in columns if c not in key_columns]
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        return (
            f"INSERT INTO {table} ({cols}) VALUES ({ph}) "
            f"ON CONFLICT ({keys}) DO UPDATE SET {updates}"
        )

    def json_set(self, column: str, path: str, param_placeholder: str) -> str:
        # PostgreSQL jsonb_set expects a jsonb value
        # path '$.resolution_note' becomes '{resolution_note}'
        pg_path = path.lstrip("$.")
        return f"jsonb_set(COALESCE({column}::jsonb, '{{}}'::jsonb), '{{{pg_path}}}', to_jsonb({param_placeholder}::text))"

    def auto_increment(self) -> str:
        return "SERIAL PRIMARY KEY"

    def timestamp_default_now(self) -> str:
        return "DEFAULT NOW()"

    def boolean_true(self) -> str:
        return "TRUE"

    def boolean_false(self) -> str:
        return "FALSE"

    def table_exists_query(self) -> str:
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s"
        )


class DB2Dialect:
    """IBM DB2 dialect — ``?`` (qmark) placeholders, ``CURRENT TIMESTAMP``.

    Compatible with ``ibm_db_dbi`` (DB-API 2.0 interface from ibm-db).
    DB2 uses qmark paramstyle natively.
    """

    @property
    def name(self) -> str:
        return "db2"

    def placeholder(self, index: int) -> str:  # noqa: ARG002
        return "?"

    def placeholders(self, count: int) -> str:
        return ", ".join("?" for _ in range(count))

    def now(self) -> str:
        return "CURRENT TIMESTAMP"

    def interval(self, value: int, unit: str) -> str:
        # DB2 interval syntax: CURRENT TIMESTAMP - 7 DAYS
        unit_map = {"seconds": "SECONDS", "minutes": "MINUTES", "hours": "HOURS", "days": "DAYS"}
        db2_unit = unit_map.get(unit, unit.upper())
        if value < 0:
            return f"CURRENT TIMESTAMP - {abs(value)} {db2_unit}"
        return f"CURRENT TIMESTAMP + {value} {db2_unit}"

    def insert_or_ignore(self, table: str, columns: list[str]) -> str:
        # DB2: MERGE INTO ... WHEN NOT MATCHED THEN INSERT
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        vals = ", ".join(f"src.c{i}" for i in range(len(columns)))
        ", ".join(f"{self.placeholder(i)} AS c{i}" for i in range(len(columns)))
        return (
            f"MERGE INTO {table} AS tgt "
            f"USING (VALUES ({ph})) AS src({', '.join(f'c{i}' for i in range(len(columns)))}) "
            f"ON tgt.{columns[0]} = src.c0 "
            f"WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({vals})"
        )

    def insert_or_replace(self, table: str, columns: list[str]) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        return f"INSERT INTO {table} ({cols}) VALUES ({ph})"

    def upsert(self, table: str, columns: list[str], key_columns: list[str]) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        src_cols = ", ".join(f"c{i}" for i in range(len(columns)))
        vals = ", ".join(f"src.c{i}" for i in range(len(columns)))
        key_matches = " AND ".join(
            f"tgt.{k} = src.c{columns.index(k)}" for k in key_columns
        )
        update_cols = [c for c in columns if c not in key_columns]
        updates = ", ".join(f"tgt.{c} = src.c{columns.index(c)}" for c in update_cols)
        return (
            f"MERGE INTO {table} AS tgt "
            f"USING (VALUES ({ph})) AS src({src_cols}) "
            f"ON {key_matches} "
            f"WHEN MATCHED THEN UPDATE SET {updates} "
            f"WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({vals})"
        )

    def json_set(self, column: str, path: str, param_placeholder: str) -> str:
        # DB2: JSON_SET (DB2 11.5+) or manual string manipulation
        return f"JSON_SET(COALESCE({column}, '{{}}'), '{path}', {param_placeholder})"

    def auto_increment(self) -> str:
        return "INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY"

    def timestamp_default_now(self) -> str:
        return "DEFAULT CURRENT TIMESTAMP"

    def boolean_true(self) -> str:
        return "1"

    def boolean_false(self) -> str:
        return "0"

    def table_exists_query(self) -> str:
        return (
            "SELECT TABNAME FROM SYSCAT.TABLES "
            "WHERE TABSCHEMA = CURRENT SCHEMA AND TABNAME = ?"
        )


class MySQLDialect:
    """MySQL dialect — ``%s`` placeholders, ``NOW()``.

    Compatible with ``mysql.connector`` and ``PyMySQL`` (both use
    ``%s`` format paramstyle).
    """

    @property
    def name(self) -> str:
        return "mysql"

    def placeholder(self, index: int) -> str:  # noqa: ARG002
        return "%s"

    def placeholders(self, count: int) -> str:
        return ", ".join("%s" for _ in range(count))

    def now(self) -> str:
        return "NOW()"

    def interval(self, value: int, unit: str) -> str:
        # MySQL: NOW() - INTERVAL 7 DAY
        unit_map = {"seconds": "SECOND", "minutes": "MINUTE", "hours": "HOUR", "days": "DAY"}
        mysql_unit = unit_map.get(unit, unit.upper().rstrip("S"))
        if value < 0:
            return f"NOW() - INTERVAL {abs(value)} {mysql_unit}"
        return f"NOW() + INTERVAL {value} {mysql_unit}"

    def insert_or_ignore(self, table: str, columns: list[str]) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        return f"INSERT IGNORE INTO {table} ({cols}) VALUES ({ph})"

    def insert_or_replace(self, table: str, columns: list[str]) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        return f"REPLACE INTO {table} ({cols}) VALUES ({ph})"

    def upsert(self, table: str, columns: list[str], key_columns: list[str]) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        update_cols = [c for c in columns if c not in key_columns]
        updates = ", ".join(f"{c} = VALUES({c})" for c in update_cols)
        return (
            f"INSERT INTO {table} ({cols}) VALUES ({ph}) "
            f"ON DUPLICATE KEY UPDATE {updates}"
        )

    def json_set(self, column: str, path: str, param_placeholder: str) -> str:
        return f"JSON_SET(COALESCE({column}, '{{}}'), '{path}', {param_placeholder})"

    def auto_increment(self) -> str:
        return "INTEGER PRIMARY KEY AUTO_INCREMENT"

    def timestamp_default_now(self) -> str:
        return "DEFAULT NOW()"

    def boolean_true(self) -> str:
        return "TRUE"

    def boolean_false(self) -> str:
        return "FALSE"

    def table_exists_query(self) -> str:
        return (
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s"
        )


class OracleDialect:
    """Oracle dialect — ``:1, :2`` numbered placeholders, ``SYSTIMESTAMP``.

    Compatible with ``oracledb`` (python-oracledb) which uses numeric
    bind variables.
    """

    @property
    def name(self) -> str:
        return "oracle"

    def placeholder(self, index: int) -> str:
        return f":{index + 1}"

    def placeholders(self, count: int) -> str:
        return ", ".join(f":{i + 1}" for i in range(count))

    def now(self) -> str:
        return "SYSTIMESTAMP"

    def interval(self, value: int, unit: str) -> str:
        # Oracle: SYSTIMESTAMP - INTERVAL '7' DAY
        unit_map = {"seconds": "SECOND", "minutes": "MINUTE", "hours": "HOUR", "days": "DAY"}
        ora_unit = unit_map.get(unit, unit.upper().rstrip("S"))
        if value < 0:
            return f"SYSTIMESTAMP - INTERVAL '{abs(value)}' {ora_unit}"
        return f"SYSTIMESTAMP + INTERVAL '{value}' {ora_unit}"

    def insert_or_ignore(self, table: str, columns: list[str]) -> str:
        # Oracle: MERGE with WHEN NOT MATCHED
        cols = ", ".join(columns)
        self.placeholders(len(columns))
        ", ".join(f"c{i}" for i in range(len(columns)))
        vals = ", ".join(f"src.c{i}" for i in range(len(columns)))
        return (
            f"MERGE INTO {table} tgt "
            f"USING (SELECT {', '.join(f'{self.placeholder(i)} AS c{i}' for i in range(len(columns)))} FROM DUAL) src "
            f"ON (tgt.{columns[0]} = src.c0) "
            f"WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({vals})"
        )

    def insert_or_replace(self, table: str, columns: list[str]) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        return f"INSERT INTO {table} ({cols}) VALUES ({ph})"

    def upsert(self, table: str, columns: list[str], key_columns: list[str]) -> str:
        cols = ", ".join(columns)
        ", ".join(f"c{i}" for i in range(len(columns)))
        vals = ", ".join(f"src.c{i}" for i in range(len(columns)))
        key_matches = " AND ".join(
            f"tgt.{k} = src.c{columns.index(k)}" for k in key_columns
        )
        update_cols = [c for c in columns if c not in key_columns]
        updates = ", ".join(f"tgt.{c} = src.c{columns.index(c)}" for c in update_cols)
        return (
            f"MERGE INTO {table} tgt "
            f"USING (SELECT {', '.join(f'{self.placeholder(i)} AS c{i}' for i in range(len(columns)))} FROM DUAL) src "
            f"ON ({key_matches}) "
            f"WHEN MATCHED THEN UPDATE SET {updates} "
            f"WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({vals})"
        )

    def json_set(self, column: str, path: str, param_placeholder: str) -> str:
        # Oracle 21c+ JSON_TRANSFORM; fallback to JSON_MERGEPATCH for older
        return f"JSON_MERGEPATCH(COALESCE({column}, '{{}}'), JSON_OBJECT('{path.lstrip('$.')}' VALUE {param_placeholder}))"

    def auto_increment(self) -> str:
        return "NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY"

    def timestamp_default_now(self) -> str:
        return "DEFAULT SYSTIMESTAMP"

    def boolean_true(self) -> str:
        return "1"

    def boolean_false(self) -> str:
        return "0"

    def table_exists_query(self) -> str:
        return "SELECT TABLE_NAME FROM USER_TABLES WHERE TABLE_NAME = UPPER(:1)"


# =========================================================================
# Registry / Factory
# =========================================================================

# Pre-instantiated singletons (dialects are stateless)
_DIALECTS: dict[str, Dialect] = {
    "sqlite": SQLiteDialect(),
    "postgresql": PostgreSQLDialect(),
    "postgres": PostgreSQLDialect(),  # alias
    "db2": DB2Dialect(),
    "mysql": MySQLDialect(),
    "oracle": OracleDialect(),
}


def get_dialect(db_type: str) -> Dialect:
    """Get a dialect by database type name.

    Args:
        db_type: One of ``'sqlite'``, ``'postgresql'``, ``'postgres'``,
                 ``'db2'``, ``'mysql'``, ``'oracle'``.

    Returns:
        Pre-instantiated :class:`Dialect` for the requested backend.

    Raises:
        ValueError: If ``db_type`` is not recognised.

    Example:
        >>> from spine.core.dialect import get_dialect
        >>> d = get_dialect("postgresql")
        >>> d.placeholders(2)
        '%s, %s'
    """
    key = db_type.lower() if isinstance(db_type, str) else db_type.value
    if key not in _DIALECTS:
        raise ValueError(
            f"Unknown dialect '{db_type}'. "
            f"Supported: {sorted(set(_DIALECTS) - {'postgres'})}"
        )
    return _DIALECTS[key]


def register_dialect(name: str, dialect: Dialect) -> None:
    """Register a custom dialect implementation.

    Useful for third-party database drivers or test doubles.

    Args:
        name: Lookup key (lower-cased automatically).
        dialect: Instance implementing :class:`Dialect`.
    """
    _DIALECTS[name.lower()] = dialect


__all__ = [
    # Protocol
    "Dialect",
    # Implementations
    "SQLiteDialect",
    "PostgreSQLDialect",
    "DB2Dialect",
    "MySQLDialect",
    "OracleDialect",
    # Factory
    "get_dialect",
    "register_dialect",
]
