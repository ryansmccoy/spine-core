"""Pytest fixtures for scheduling tests."""

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def db_conn():
    """Create an in-memory SQLite database with scheduler schema."""
    conn = sqlite3.connect(":memory:")
    
    # Load scheduler schema
    schema_path = Path(__file__).parent.parent.parent / "src" / "spine" / "core" / "schema" / "03_scheduler.sql"
    if schema_path.exists():
        with open(schema_path) as f:
            conn.executescript(f.read())
    else:
        # Inline schema if file not found
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS core_schedules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                target_type TEXT NOT NULL DEFAULT 'operation',
                target_name TEXT NOT NULL,
                params TEXT,
                schedule_type TEXT NOT NULL DEFAULT 'cron',
                cron_expression TEXT,
                interval_seconds INTEGER,
                run_at TEXT,
                timezone TEXT NOT NULL DEFAULT 'UTC',
                enabled INTEGER NOT NULL DEFAULT 1,
                max_instances INTEGER NOT NULL DEFAULT 1,
                misfire_grace_seconds INTEGER NOT NULL DEFAULT 60,
                last_run_at TEXT,
                next_run_at TEXT,
                last_run_status TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                created_by TEXT,
                version INTEGER NOT NULL DEFAULT 1
            );
            
            CREATE TABLE IF NOT EXISTS core_schedule_runs (
                id TEXT PRIMARY KEY,
                schedule_id TEXT NOT NULL,
                schedule_name TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                run_id TEXT,
                execution_id TEXT,
                error TEXT,
                skip_reason TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            
            CREATE TABLE IF NOT EXISTS core_schedule_locks (
                schedule_id TEXT PRIMARY KEY,
                locked_by TEXT NOT NULL,
                locked_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
        """)
    
    yield conn
    conn.close()


@pytest.fixture
def repository(db_conn):
    """Create a ScheduleRepository with test database."""
    from spine.core.scheduling import ScheduleRepository
    return ScheduleRepository(db_conn)


@pytest.fixture
def lock_manager(db_conn):
    """Create a LockManager with test database."""
    from spine.core.scheduling import LockManager
    return LockManager(db_conn, instance_id="test-instance")


@pytest.fixture
def backend():
    """Create a ThreadSchedulerBackend."""
    from spine.core.scheduling import ThreadSchedulerBackend
    return ThreadSchedulerBackend()


@pytest.fixture
def scheduler_service(backend, repository, lock_manager):
    """Create a SchedulerService for testing."""
    from spine.core.scheduling import SchedulerService
    return SchedulerService(
        backend=backend,
        repository=repository,
        lock_manager=lock_manager,
        dispatcher=None,  # No dispatcher for unit tests
        interval_seconds=1.0,  # Fast interval for tests
    )
