"""SQLite database connection and migration management."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import structlog

from market_spine.config import get_settings
from spine.framework.db import set_connection_provider

logger = structlog.get_logger()

# Global connection for simple sync usage
_connection: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """Get or create database connection."""
    global _connection
    if _connection is None:
        settings = get_settings()
        _connection = sqlite3.connect(
            settings.database_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit mode, we manage transactions explicitly
        )
        _connection.row_factory = sqlite3.Row
        # Enable foreign keys
        _connection.execute("PRAGMA foreign_keys = ON")
    return _connection


def init_connection_provider() -> None:
    """Initialize the framework connection provider with SQLite connection."""
    set_connection_provider(get_connection)


def close_connection() -> None:
    """Close database connection."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Context manager for database transactions."""
    conn = get_connection()
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def init_db() -> None:
    """Initialize database with migrations."""
    migrations_dir = Path(__file__).parent.parent.parent.parent / "migrations"

    if not migrations_dir.exists():
        # Try relative to current working directory
        migrations_dir = Path("migrations")

    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")

    conn = get_connection()

    # Create migrations tracking table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Get applied migrations
    applied = {row["filename"] for row in conn.execute("SELECT filename FROM _migrations")}

    # Get migration files
    migration_files = sorted(migrations_dir.glob("*.sql"))

    for migration_file in migration_files:
        if migration_file.name in applied:
            logger.debug("migration_already_applied", filename=migration_file.name)
            continue

        logger.info("applying_migration", filename=migration_file.name)
        sql = migration_file.read_text()

        # executescript manages its own transactions, so we run it directly
        # then record the migration separately
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO _migrations (filename) VALUES (?)",
            (migration_file.name,),
        )

        logger.info("migration_applied", filename=migration_file.name)


def reset_db() -> None:
    """Reset database (for testing)."""
    settings = get_settings()
    close_connection()
    if settings.database_path.exists():
        settings.database_path.unlink()
