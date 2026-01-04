"""Pytest configuration and fixtures."""

import os
import pytest
from pathlib import Path

# Set test environment - only set if not already set
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "postgresql://spine:spine@localhost:5432/spine"
if "REDIS_URL" not in os.environ:
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
if "CELERY_BROKER_URL" not in os.environ:
    os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
if "CELERY_RESULT_BACKEND" not in os.environ:
    os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/1"
if "LOG_LEVEL" not in os.environ:
    os.environ["LOG_LEVEL"] = "WARNING"


# Global pool for all tests
_pool = None


def get_test_pool():
    """Get or create the test connection pool."""
    global _pool
    if _pool is None:
        from market_spine.core.database import init_pool

        _pool = init_pool()

        # Run migrations
        migrations_dir = Path(__file__).parent.parent / "migrations"
        if migrations_dir.exists():
            with _pool.connection() as conn:
                with conn.cursor() as cur:
                    # Create migrations table
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS _migrations (
                            name TEXT PRIMARY KEY,
                            applied_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    conn.commit()

                    # Get applied migrations
                    cur.execute("SELECT name FROM _migrations")
                    applied = {row[0] for row in cur.fetchall()}

                    # Apply migrations
                    for migration_file in sorted(migrations_dir.glob("*.sql")):
                        if migration_file.name not in applied:
                            sql = migration_file.read_text()
                            try:
                                cur.execute(sql)
                                cur.execute(
                                    "INSERT INTO _migrations (name) VALUES (%s)",
                                    (migration_file.name,),
                                )
                                conn.commit()
                            except Exception as e:
                                conn.rollback()
                                print(f"Migration error {migration_file.name}: {e}")
    return _pool


@pytest.fixture(scope="session")
def db_pool():
    """Create database connection pool for tests."""
    pool = get_test_pool()
    yield pool
    # Don't close - let it be reused


@pytest.fixture
def db_conn(db_pool):
    """Get a database connection for a test."""
    with db_pool.connection() as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def clean_db(db_pool):
    """Clean test data before each test."""
    with db_pool.connection() as conn:
        with conn.cursor() as cur:
            # Clean in order due to foreign keys
            cur.execute("DELETE FROM execution_events")
            cur.execute("DELETE FROM dead_letters")
            cur.execute("DELETE FROM concurrency_locks")
            cur.execute("DELETE FROM executions")
            conn.commit()
        yield


@pytest.fixture
def local_backend():
    """Create local backend for testing."""
    from market_spine.backends.local_backend import LocalBackend

    backend = LocalBackend()
    yield backend
    backend.clear()


@pytest.fixture
def ledger(db_conn):
    """Create execution ledger."""
    from market_spine.execution.ledger import ExecutionLedger

    return ExecutionLedger(conn=db_conn)


@pytest.fixture
def dispatcher(ledger, local_backend):
    """Create dispatcher with local backend."""
    from market_spine.execution.dispatcher import Dispatcher

    return Dispatcher(ledger, local_backend)


@pytest.fixture
def dlq_manager(db_conn):
    """Create DLQ manager."""
    from market_spine.execution.dlq import DLQManager

    return DLQManager(conn=db_conn)
