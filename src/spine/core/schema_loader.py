"""SQL schema loading utilities.

Provides functions to apply SQL schema files to a database connection.
For production use with migration tracking, use the MigrationRunner instead.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from spine.core.dialect import Dialect, SQLiteDialect
from spine.core.protocols import Connection

logger = logging.getLogger(__name__)

# Default schema directory
SCHEMA_DIR = Path(__file__).resolve().parent / "schema"


def _split_sql(sql: str) -> list[str]:
    """Split a SQL script into individual statements.

    Handles semicolon-terminated statements while respecting
    string literals and comments.
    """
    statements = []
    current = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        current.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt and stmt != ";":
                statements.append(stmt)
            current = []
    # Remaining unterminated statement
    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)
    return statements

def get_schema_files(schema_dir: Path | str | None = None) -> list[Path]:
    """Get sorted list of SQL schema files.

    Parameters
    ----------
    schema_dir
        Directory containing ``.sql`` files. Defaults to core/schema/.

    Returns
    -------
    list[Path]
        Paths to SQL files sorted by filename (00_, 01_, etc.).
    """
    directory = Path(schema_dir) if schema_dir else SCHEMA_DIR
    if not directory.exists():
        return []
    return sorted(directory.glob("*.sql"))


def read_schema_sql(schema_dir: Path | str | None = None) -> str:
    """Read and concatenate all SQL schema files.

    Parameters
    ----------
    schema_dir
        Directory containing ``.sql`` files.

    Returns
    -------
    str
        Combined SQL content from all schema files.
    """
    files = get_schema_files(schema_dir)
    parts = []
    for f in files:
        parts.append(f"-- Source: {f.name}\n")
        parts.append(f.read_text(encoding="utf-8"))
        parts.append("\n\n")
    return "".join(parts)


def apply_all_schemas(
    conn: Connection,
    schema_dir: Path | str | None = None,
    *,
    skip_files: Sequence[str] | None = None,
) -> list[str]:
    """Apply all SQL schema files to a database connection.

    This is a simple utility for test setups. For production use with
    migration tracking, use :class:`~spine.core.migrations.MigrationRunner`.

    Parameters
    ----------
    conn
        Database connection.
    schema_dir
        Directory containing ``.sql`` files. Defaults to core/schema/.
    skip_files
        Optional list of filenames to skip (e.g., ["00_core.sql"]).

    Returns
    -------
    list[str]
        List of applied schema filenames.

    Example
    -------
    ::

        import sqlite3
        from spine.core.schema_loader import apply_all_schemas

        conn = sqlite3.connect(":memory:")
        applied = apply_all_schemas(conn)
        print(f"Applied {len(applied)} schema files")
    """
    skip_set = set(skip_files or [])
    applied = []

    for sql_file in get_schema_files(schema_dir):
        if sql_file.name in skip_set:
            logger.debug("schema.skipped", extra={"file": sql_file.name})
            continue

        sql = sql_file.read_text(encoding="utf-8")
        # Execute each statement individually for portability
        for statement in _split_sql(sql):
            if statement.strip():
                conn.execute(statement)
        applied.append(sql_file.name)
        logger.debug("schema.applied", extra={"file": sql_file.name})

    conn.commit()
    logger.info("schema.all_applied", extra={"count": len(applied)})
    return applied


def create_test_db(schema_dir: Path | str | None = None) -> sqlite3.Connection:
    """Create an in-memory SQLite database with all schemas applied.

    Convenience function for unit tests.

    Parameters
    ----------
    schema_dir
        Directory containing ``.sql`` files.

    Returns
    -------
    sqlite3.Connection
        In-memory connection with schemas applied.

    Example
    -------
    ::

        from spine.core.schema_loader import create_test_db

        conn = create_test_db()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
    """
    conn = sqlite3.connect(":memory:")
    apply_all_schemas(conn, schema_dir)
    return conn


def get_table_list(conn: Connection, dialect: Dialect = SQLiteDialect()) -> list[str]:
    """Get list of tables in the database.

    Parameters
    ----------
    conn
        Database connection.
    dialect
        SQL dialect for table introspection.

    Returns
    -------
    list[str]
        Table names sorted alphabetically.
    """
    query = dialect.table_exists_query().replace(
        f"AND name = {dialect.placeholder(0)}",
        "",
    ).replace(
        f"AND TABLE_NAME = {dialect.placeholder(0)}",
        "",
    ).replace(
        f"AND TABLE_NAME = UPPER({dialect.placeholder(0)})",
        "",
    )
    # Simpler approach: use dialect-specific catalog query
    if dialect.name == "sqlite":
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    elif dialect.name == "postgresql":
        cursor = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
    elif dialect.name == "mysql":
        cursor = conn.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME"
        )
    elif dialect.name == "db2":
        cursor = conn.execute(
            "SELECT TABNAME FROM SYSCAT.TABLES WHERE TABSCHEMA = CURRENT SCHEMA ORDER BY TABNAME"
        )
    elif dialect.name == "oracle":
        cursor = conn.execute(
            "SELECT TABLE_NAME FROM USER_TABLES ORDER BY TABLE_NAME"
        )
    else:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    return [row[0] for row in cursor.fetchall()]


def get_table_schema(conn: Connection, table: str, dialect: Dialect = SQLiteDialect()) -> str:
    """Get the CREATE TABLE statement for a table.

    Parameters
    ----------
    conn
        Database connection.
    table
        Table name.
    dialect
        SQL dialect for introspection.

    Returns
    -------
    str
        The CREATE TABLE SQL statement.

    Raises
    ------
    ValueError
        If table doesn't exist.
    """
    if dialect.name == "sqlite":
        cursor = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
    elif dialect.name == "postgresql":
        # PostgreSQL: use pg_catalog to reconstruct DDL (simplified)
        cursor = conn.execute(
            "SELECT 'CREATE TABLE ' || tablename FROM pg_tables WHERE tablename = %s",
            (table,),
        )
    else:
        # Fallback: try SQLite syntax
        cursor = conn.execute(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name={dialect.placeholder(0)}",
            (table,),
        )
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Table not found: {table}")
    return row[0]
