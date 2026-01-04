"""PostgreSQL database connection and migration management using psycopg3."""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import structlog
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from market_spine.config import get_settings

logger = structlog.get_logger()

# Global connection pool
_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Get or create connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            settings.database_url,
            min_size=2,
            max_size=10,
            kwargs={"row_factory": dict_row},
        )
    return _pool


def close_pool() -> None:
    """Close connection pool."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_connection() -> Iterator[Connection]:
    """Get a connection from the pool."""
    with get_pool().connection() as conn:
        yield conn


@contextmanager
def transaction() -> Iterator[Connection]:
    """Context manager for database transactions."""
    with get_connection() as conn:
        with conn.transaction():
            yield conn


def init_db() -> None:
    """Initialize database with migrations."""
    # Try multiple paths for migrations directory
    possible_paths = [
        Path(__file__).parent.parent.parent.parent / "migrations",
        Path(__file__).parent.parent.parent / "migrations",
        Path("migrations"),
    ]

    migrations_dir = None
    for path in possible_paths:
        if path.exists():
            migrations_dir = path
            break

    if migrations_dir is None:
        raise FileNotFoundError(f"Migrations directory not found. Tried: {possible_paths}")

    logger.info("running_migrations", migrations_dir=str(migrations_dir))

    with get_connection() as conn:
        # Create migrations tracking table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.commit()

        # Get applied migrations
        result = conn.execute("SELECT filename FROM _migrations")
        applied = {row["filename"] for row in result.fetchall()}

        # Get migration files
        migration_files = sorted(migrations_dir.glob("*.sql"))

        for migration_file in migration_files:
            if migration_file.name in applied:
                logger.debug("migration_already_applied", filename=migration_file.name)
                continue

            logger.info("applying_migration", filename=migration_file.name)
            migration_sql = migration_file.read_text()

            # Execute migration
            conn.execute(migration_sql)
            conn.execute(
                "INSERT INTO _migrations (filename) VALUES (%s)",
                (migration_file.name,),
            )
            conn.commit()

            logger.info("migration_applied", filename=migration_file.name)
