"""Pytest configuration and fixtures."""

import os
import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    # Use SQLite for testing (simpler, no Docker needed)
    os.environ.setdefault("DATABASE_URL", "sqlite:///test_market_spine.db")
    os.environ.setdefault("BACKEND_TYPE", "local")
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    yield
    # Cleanup
    if os.path.exists("test_market_spine.db"):
        os.remove("test_market_spine.db")


@pytest.fixture
def sample_trade_data():
    """Sample trade data for testing."""
    return [
        {
            "trade_id": "TEST001",
            "symbol": "ACME",
            "trade_date": "2024-01-02",
            "price": "100.50",
            "size": "1000",
            "side": "BUY",
            "venue": "VENUE_A",
        },
        {
            "trade_id": "TEST002",
            "symbol": "ACME",
            "trade_date": "2024-01-02",
            "price": "100.75",
            "size": "500",
            "side": "SELL",
            "venue": "VENUE_B",
        },
        {
            "trade_id": "TEST003",
            "symbol": "BOLT",
            "trade_date": "2024-01-02",
            "price": "50.00",
            "size": "2000",
            "side": "BUY",
            "venue": "VENUE_A",
        },
    ]
