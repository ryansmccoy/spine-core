# src/market_spine/domains/otc/models.py

"""
OTC Weekly Transparency - Shared Data Models

These models are IDENTICAL across all tiers (basic, intermediate, advanced, full).
Copy this file directly - don't try to share via package dependencies.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


# =============================================================================
# ENUMS (frozen values - never change these strings)
# =============================================================================


class Tier(str, Enum):
    """FINRA market tier classification."""

    NMS_TIER_1 = "NMS Tier 1"
    NMS_TIER_2 = "NMS Tier 2"
    OTC = "OTC"

    @classmethod
    def from_finra(cls, value: str) -> "Tier":
        """Parse tier from FINRA file value."""
        return cls(value)  # FINRA uses exact same strings


# =============================================================================
# RAW DATA (from FINRA file, before any processing)
# =============================================================================


@dataclass
class RawRecord:
    """
    One row from a FINRA OTC weekly transparency file.

    This is the raw data exactly as FINRA provides it,
    with only minimal parsing (strings to typed values).
    """

    # FINRA columns
    tier: str  # "NMS Tier 1", "NMS Tier 2", "OTC"
    symbol: str  # Stock ticker (e.g., "AAPL")
    issue_name: str  # Company name
    venue_name: str  # Full venue name
    mpid: str  # 4-char venue code
    share_volume: int  # Shares traded
    trade_count: int  # Number of trades
    week_ending: date  # Friday of reporting week

    # Computed on parse
    record_hash: str = field(default="")

    def __post_init__(self):
        if not self.record_hash:
            self.record_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Deterministic hash for deduplication."""
        key = f"{self.week_ending.isoformat()}|{self.tier}|{self.symbol}|{self.mpid}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]


# =============================================================================
# NORMALIZED DATA (cleaned and validated)
# =============================================================================


@dataclass
class VenueVolume:
    """
    Normalized venue trading volume for one symbol-venue-week.

    This is the primary analytical unit:
    "How much did venue X trade of symbol Y in week Z?"
    """

    week_ending: date
    tier: Tier
    symbol: str
    mpid: str
    share_volume: int
    trade_count: int
    avg_trade_size: Decimal | None = None
    record_hash: str = ""

    def __post_init__(self):
        # Calculate avg trade size if not provided
        if self.avg_trade_size is None and self.trade_count > 0:
            self.avg_trade_size = Decimal(self.share_volume) / Decimal(self.trade_count)


# =============================================================================
# AGGREGATED DATA (computed summaries)
# =============================================================================


@dataclass
class SymbolSummary:
    """
    Weekly summary for one symbol across all venues.

    Answers: "What was total activity for AAPL this week?"
    """

    week_ending: date
    tier: Tier
    symbol: str
    total_volume: int
    total_trades: int
    venue_count: int
    avg_trade_size: Decimal | None = None


@dataclass
class VenueShare:
    """
    Weekly market share for one venue.

    Answers: "What % of volume did SGMT handle this week?"
    """

    week_ending: date
    mpid: str
    total_volume: int
    total_trades: int
    symbol_count: int
    market_share_pct: Decimal
    rank: int = 0


# =============================================================================
# PIPELINE RESULTS
# =============================================================================


@dataclass
class IngestResult:
    """Result of ingesting a file."""

    batch_id: str
    file_path: str
    record_count: int
    inserted: int
    duplicates: int


@dataclass
class NormalizeResult:
    """Result of normalizing raw records."""

    processed: int
    accepted: int
    rejected: int
    records: list[VenueVolume] = field(default_factory=list)
