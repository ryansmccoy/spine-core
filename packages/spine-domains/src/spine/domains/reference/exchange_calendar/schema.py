"""
Schema definitions for Exchange Calendar domain.

Follows the same pattern as FINRA OTC:
- DOMAIN constant for manifest/rejects/quality
- TABLES dict for table names
- Exchange enum for valid exchange codes
"""

from enum import Enum


# Domain identifier for core_manifest, core_rejects, core_quality
DOMAIN = "reference.exchange_calendar"


class Exchange(str, Enum):
    """ISO 10383 Market Identifier Codes for supported exchanges."""
    
    XNYS = "XNYS"  # New York Stock Exchange
    XNAS = "XNAS"  # NASDAQ
    XASE = "XASE"  # NYSE American (formerly AMEX)
    ARCX = "ARCX"  # NYSE Arca
    BATS = "BATS"  # Cboe BZX Exchange
    
    @classmethod
    def values(cls) -> list[str]:
        return [e.value for e in cls]


# Stage names for pipeline manifest tracking
class Stage(str, Enum):
    """Processing stages for exchange calendar data."""
    
    RAW = "raw"
    COMPUTED = "computed"


# Table names following naming convention: {domain_key}_{entity}
TABLES = {
    "holidays": "reference_exchange_calendar_holidays",
    "trading_days": "reference_exchange_calendar_trading_days",
}


# Partition key format for manifest
def partition_key(year: int, exchange_code: str) -> str:
    """
    Generate partition key for manifest tracking.
    
    Format: {"year": 2025, "exchange_code": "XNYS"}
    """
    import json
    return json.dumps({"year": year, "exchange_code": exchange_code}, sort_keys=True)
