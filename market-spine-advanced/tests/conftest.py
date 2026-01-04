"""Pytest configuration and fixtures."""

import os
import pytest
import psycopg
from datetime import date
from decimal import Decimal

# Set test environment variables before importing app modules
os.environ.setdefault("DATABASE_URL", "postgresql://spine:spine@localhost:5432/market_spine_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("BACKEND", "local")
os.environ.setdefault("STORAGE_TYPE", "local")
os.environ.setdefault("STORAGE_LOCAL_PATH", "/tmp/spine_test_storage")
os.environ.setdefault("OTC_API_USE_MOCK", "true")


@pytest.fixture(scope="session")
def database_url():
    """Get database URL for testing."""
    return os.environ["DATABASE_URL"]


@pytest.fixture(scope="session")
def db_setup(database_url):
    """Create test database schema."""
    from pathlib import Path

    migrations_dir = Path(__file__).parent.parent / "migrations"

    print(f"DEBUG: Looking for migrations in {migrations_dir}")
    print(f"DEBUG: migrations_dir exists: {migrations_dir.exists()}")

    with psycopg.connect(database_url) as conn:
        # Drop existing tables for clean test run
        conn.execute("""
            DROP TABLE IF EXISTS execution_events CASCADE;
            DROP TABLE IF EXISTS executions CASCADE;
            DROP TABLE IF EXISTS pipeline_schedules CASCADE;
            DROP TABLE IF EXISTS stored_files CASCADE;
            DROP TABLE IF EXISTS otc_metrics_daily CASCADE;
            DROP TABLE IF EXISTS otc_trades CASCADE;
            DROP TABLE IF EXISTS otc_trades_raw CASCADE;
            DROP TABLE IF EXISTS _migrations CASCADE;
        """)
        conn.commit()

        # Apply migrations
        migration_files = sorted(migrations_dir.glob("*.sql"))
        print(f"DEBUG: Found {len(migration_files)} migration files")

        for migration_file in migration_files:
            print(f"DEBUG: Applying migration {migration_file.name}")
            sql = migration_file.read_text()
            conn.execute(sql)

        conn.commit()

    yield database_url

    # Cleanup not needed - each test uses transactions


@pytest.fixture
def db_conn(db_setup):
    """Get database connection with transaction rollback."""
    from market_spine.db import get_pool, close_pool
    from market_spine.config import get_settings
    import os

    # Ensure settings use test database
    os.environ["DATABASE_URL"] = db_setup

    # Force pool recreation with test database
    close_pool()
    get_pool()  # Initialize pool

    yield

    close_pool()


@pytest.fixture
def clean_tables(db_conn, database_url):
    """Clean all tables before test."""
    with psycopg.connect(database_url) as conn:
        conn.execute("DELETE FROM execution_events")
        conn.execute("DELETE FROM executions")
        conn.execute("DELETE FROM schedules")
        conn.execute("DELETE FROM stored_files")
        conn.execute("DELETE FROM otc_metrics_daily")
        conn.execute("DELETE FROM otc_trades")
        conn.execute("DELETE FROM otc_trades_raw")
        conn.commit()

    yield


@pytest.fixture
def sample_trades():
    """Sample trade data for testing."""
    return [
        {
            "trade_id": "T001",
            "symbol": "AAPL",
            "trade_date": date(2024, 1, 15),
            "price": Decimal("185.50"),
            "size": Decimal("1000"),
            "side": "buy",
            "venue": "TEST",
        },
        {
            "trade_id": "T002",
            "symbol": "AAPL",
            "trade_date": date(2024, 1, 15),
            "price": Decimal("186.00"),
            "size": Decimal("500"),
            "side": "sell",
            "venue": "TEST",
        },
        {
            "trade_id": "T003",
            "symbol": "GOOGL",
            "trade_date": date(2024, 1, 15),
            "price": Decimal("142.25"),
            "size": Decimal("200"),
            "side": "buy",
            "venue": "TEST",
        },
    ]


@pytest.fixture
def sample_raw_trades():
    """Sample raw trade data for normalization testing."""
    return [
        {
            "tradeId": "RAW001",
            "ticker": "MSFT",
            "Date": "2024-01-16",
            "Price": "380.50",
            "quantity": "100",
            "direction": "buy",
            "ATS": "DARK1",
        },
        {
            "trade_id": "RAW002",
            "symbol": "TSLA",
            "trade_date": "2024-01-16",
            "price": 225.75,
            "size": 50,
            "side": "sell",
            "venue": "DARK2",
        },
    ]


@pytest.fixture
def mock_storage(tmp_path):
    """Create mock local storage."""
    storage_path = tmp_path / "storage"
    storage_path.mkdir()

    os.environ["STORAGE_LOCAL_PATH"] = str(storage_path)

    yield storage_path


@pytest.fixture
def api_client(db_conn, clean_tables):
    """FastAPI test client."""
    from fastapi.testclient import TestClient
    from market_spine.api.main import app

    # Override lifespan since we already init'd pool
    return TestClient(app, raise_server_exceptions=True)
