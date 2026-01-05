"""
Market Data Domain

Provides price data from external market data providers (Alpha Vantage, etc.).

Pipelines:
- market_data.ingest_prices: Fetch daily OHLCV for a symbol

Usage:
    spine run market_data.ingest_prices -p symbol=AAPL
"""

# Import pipelines to register them
from . import pipelines  # noqa: F401

__all__ = ["sources", "schema", "pipelines"]
