"""
Market data sources - provider-agnostic price data fetching.

Sources are registered via @register_source decorator and resolved
at runtime via create_source() factory based on environment config.

Available sources:
- alpha_vantage: Alpha Vantage API (free tier: 25 req/day, 5 req/min)
- polygon: (future) Polygon.io API
- yahoo: (future) Yahoo Finance

Usage:
    source = create_source()  # Auto-detect from env
    source = create_source("alpha_vantage")  # Explicit
    result = source.fetch({"symbol": "AAPL"})
    data, anomalies, metadata = result.data, result.anomalies, result.metadata
"""

import os
from abc import ABC, abstractmethod
from typing import Any

from .alpha_vantage import (
    AlphaVantageSource,
    FetchResult,
    SourceMetadata,
)


class IngestionError(Exception):
    """Raised when data ingestion fails."""
    pass


class PriceSource(ABC):
    """Abstract base for price data sources."""

    @abstractmethod
    def fetch(self, params: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """
        Fetch price data.
        
        Returns:
            (data, anomalies) tuple where:
            - data: List of OHLCV dicts
            - anomalies: List of anomaly dicts (rate limits, errors, etc.)
        """
        ...

    @abstractmethod
    def validate_config(self) -> tuple[bool, str | None]:
        """Validate source configuration. Returns (is_valid, error_message)."""
        ...


# Source registry
_SOURCE_REGISTRY: dict[str, type] = {
    "alpha_vantage": AlphaVantageSource,
}


def register_source(name: str):
    """Decorator to register a price source."""
    def decorator(cls):
        _SOURCE_REGISTRY[name] = cls
        return cls
    return decorator


def list_sources() -> list[str]:
    """List available source names."""
    return list(_SOURCE_REGISTRY.keys())


def create_source(source_type: str | None = None) -> PriceSource:
    """
    Factory to create a price source based on type or environment.
    
    If source_type is None, auto-detects from environment variables:
    - ALPHA_VANTAGE_API_KEY → AlphaVantageSource
    - POLYGON_API_KEY → PolygonSource (future)
    
    Args:
        source_type: Explicit source type or None for auto-detect
        
    Returns:
        Configured price source instance
        
    Raises:
        ValueError: If no source can be configured
    """
    if source_type:
        if source_type not in _SOURCE_REGISTRY:
            available = ", ".join(_SOURCE_REGISTRY.keys())
            raise ValueError(f"Unknown source type '{source_type}'. Available: {available}")
        cls = _SOURCE_REGISTRY[source_type]
        # Get config from env based on source type
        if source_type == "alpha_vantage":
            api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
            if not api_key or api_key == "your_api_key_here":
                raise ValueError("ALPHA_VANTAGE_API_KEY not configured")
            return cls({"api_key": api_key})
        # Future sources here
        raise ValueError(f"No config handler for source type '{source_type}'")
    
    # Auto-detect from environment
    alpha_vantage_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if alpha_vantage_key and alpha_vantage_key != "your_api_key_here":
        return AlphaVantageSource({"api_key": alpha_vantage_key})
    
    # Future: Check for Polygon
    # polygon_key = os.environ.get("POLYGON_API_KEY")
    # if polygon_key:
    #     return PolygonSource({"api_key": polygon_key})
    
    raise ValueError(
        "No price data source configured. Set one of: "
        "ALPHA_VANTAGE_API_KEY, POLYGON_API_KEY"
    )


__all__ = [
    "AlphaVantageSource",
    "PriceSource", 
    "IngestionError",
    "FetchResult",
    "SourceMetadata",
    "create_source",
    "list_sources",
    "register_source",
]
