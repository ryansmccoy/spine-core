# 02: Models and Types

> **Purpose**: Define domain models, value objects, and enums used across all OTC pipelines. These types enforce domain invariants at the Python level before data touches the database.

---

## Design Choices

### Why Value Objects?
- **Early validation**: `WeekEnding("2025-12-25")` fails immediately (not a Friday)
- **Type safety**: Functions take `WeekEnding`, not `str` → IDE catches mistakes
- **Normalization**: `Symbol("aapl")` becomes `"AAPL"` automatically
- **Documentation**: Types are self-documenting

### Why Not ORM?
- Basic tier uses raw SQL for simplicity
- Models are data classes, not ORM entities
- Database is the source of truth, not Python objects

---

## File: `domains/otc/enums.py`

```python
"""
OTC Domain Enums

These enums are frozen for Basic tier and will be used across all higher tiers.
Do not add values without updating all tiers simultaneously.
"""
from enum import Enum


class Tier(str, Enum):
    """
    FINRA OTC transparency tiers.
    
    NMS_TIER_1: Stocks in S&P 500, Russell 1000, or trading > 1M shares/day avg
    NMS_TIER_2: All other NMS stocks
    OTC: Non-NMS (OTC Markets) stocks
    """
    NMS_TIER_1 = "NMS_TIER_1"
    NMS_TIER_2 = "NMS_TIER_2"
    OTC = "OTC"
    
    @classmethod
    def from_string(cls, value: str) -> "Tier":
        """Parse tier from string, case-insensitive."""
        normalized = value.strip().upper().replace(" ", "_").replace("-", "_")
        # Handle common variations
        mappings = {
            "NMS1": cls.NMS_TIER_1,
            "TIER1": cls.NMS_TIER_1,
            "NMS2": cls.NMS_TIER_2,
            "TIER2": cls.NMS_TIER_2,
        }
        if normalized in mappings:
            return mappings[normalized]
        try:
            return cls(normalized)
        except ValueError:
            raise ValueError(f"Invalid tier: '{value}'. Expected one of: {[t.value for t in cls]}")


class ManifestStage(str, Enum):
    """
    Processing stage for a week's data.
    
    Stages are ordered: PENDING < INGESTED < NORMALIZED < AGGREGATED < ROLLING < SNAPSHOT
    A week must pass through stages in order.
    """
    PENDING = "PENDING"
    INGESTED = "INGESTED"
    NORMALIZED = "NORMALIZED"
    AGGREGATED = "AGGREGATED"
    ROLLING = "ROLLING"
    SNAPSHOT = "SNAPSHOT"
    
    def __lt__(self, other: "ManifestStage") -> bool:
        order = list(ManifestStage)
        return order.index(self) < order.index(other)
    
    def __le__(self, other: "ManifestStage") -> bool:
        return self == other or self < other


class NormalizationStatus(str, Enum):
    """Status of a raw record after normalization attempt."""
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class QualityStatus(str, Enum):
    """Result of a quality check."""
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class QualityCategory(str, Enum):
    """Category of quality check."""
    INTEGRITY = "INTEGRITY"         # Data structure correctness
    COMPLETENESS = "COMPLETENESS"   # Data coverage/availability
    BUSINESS_RULE = "BUSINESS_RULE" # Domain-specific rules


class RejectStage(str, Enum):
    """Stage at which a record was rejected."""
    INGEST = "INGEST"
    NORMALIZE = "NORMALIZE"
    AGGREGATE = "AGGREGATE"


class TrendDirection(str, Enum):
    """Trend direction for rolling analysis."""
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"
```

---

## File: `domains/otc/validators.py`

```python
"""
OTC Domain Validators (Value Objects)

These classes enforce domain invariants at construction time.
If you can construct a WeekEnding, it's guaranteed to be a valid Friday.
"""
from datetime import date, timedelta
from typing import Union
import re
import hashlib


class WeekEnding:
    """
    OTC week ending date - always a Friday.
    
    FINRA publishes OTC transparency data every Friday for the previous week.
    This value object ensures all week_ending values are valid Fridays.
    
    Usage:
        week = WeekEnding("2025-12-26")  # OK - it's a Friday
        week = WeekEnding("2025-12-25")  # Raises ValueError - Thursday
        
        # From any date, find containing week's Friday
        week = WeekEnding.from_any_date(date(2025, 12, 23))  # Returns 2025-12-26
    """
    
    __slots__ = ("_value",)
    
    def __init__(self, value: Union[str, date]):
        if isinstance(value, str):
            try:
                parsed = date.fromisoformat(value)
            except ValueError as e:
                raise ValueError(f"Invalid date format '{value}': {e}")
        elif isinstance(value, date):
            parsed = value
        else:
            raise TypeError(f"Expected str or date, got {type(value).__name__}")
        
        # Friday = weekday 4
        if parsed.weekday() != 4:
            day_name = parsed.strftime("%A")
            raise ValueError(
                f"week_ending must be a Friday, got {parsed.isoformat()} ({day_name}). "
                f"Nearest Friday: {self._nearest_friday(parsed).isoformat()}"
            )
        
        self._value = parsed
    
    @staticmethod
    def _nearest_friday(d: date) -> date:
        """Find the Friday of the week containing date d."""
        days_until_friday = (4 - d.weekday()) % 7
        if days_until_friday == 0 and d.weekday() != 4:
            days_until_friday = 7
        return d + timedelta(days=days_until_friday)
    
    @classmethod
    def from_any_date(cls, d: date) -> "WeekEnding":
        """Create WeekEnding from any date, finding the containing week's Friday."""
        friday = cls._nearest_friday(d)
        return cls(friday)
    
    @classmethod
    def from_weeks_back(cls, weeks_back: int, reference_date: date = None) -> "WeekEnding":
        """
        Create WeekEnding for N weeks ago from reference date.
        
        Args:
            weeks_back: Number of weeks to go back (0 = this week)
            reference_date: Reference date (default: today)
        """
        ref = reference_date or date.today()
        # Find this week's Friday first
        this_friday = cls._nearest_friday(ref)
        # Go back N weeks
        target_friday = this_friday - timedelta(weeks=weeks_back)
        return cls(target_friday)
    
    @property
    def value(self) -> date:
        """Return the underlying date."""
        return self._value
    
    def __str__(self) -> str:
        return self._value.isoformat()
    
    def __repr__(self) -> str:
        return f"WeekEnding({self._value.isoformat()!r})"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, WeekEnding):
            return self._value == other._value
        if isinstance(other, str):
            return str(self) == other
        return False
    
    def __hash__(self) -> int:
        return hash(self._value)
    
    def __lt__(self, other: "WeekEnding") -> bool:
        return self._value < other._value


class Symbol:
    """
    Normalized stock symbol.
    
    Ensures consistent uppercase formatting and validates format.
    
    Usage:
        sym = Symbol("aapl")  # Normalized to "AAPL"
        sym = Symbol("BRK.A") # OK - dots allowed
        sym = Symbol("123")   # Raises ValueError - must start with letter
    """
    
    __slots__ = ("_value",)
    
    # Pattern: Start with letter, then alphanumeric, dots, or hyphens
    # Max length 10 (covers most symbols including warrants like "SPAC.WS")
    PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
    
    def __init__(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"Expected str, got {type(value).__name__}")
        
        normalized = value.strip().upper()
        
        if not normalized:
            raise ValueError("Symbol cannot be empty")
        
        if not self.PATTERN.match(normalized):
            raise ValueError(
                f"Invalid symbol format: '{value}'. "
                f"Must start with letter, contain only A-Z, 0-9, '.', '-', max 10 chars"
            )
        
        self._value = normalized
    
    @property
    def value(self) -> str:
        return self._value
    
    def __str__(self) -> str:
        return self._value
    
    def __repr__(self) -> str:
        return f"Symbol({self._value!r})"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, Symbol):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other.upper()
        return False
    
    def __hash__(self) -> int:
        return hash(self._value)


class MPID:
    """
    Market Participant Identifier.
    
    FINRA assigns 4-character MPIDs to market participants.
    
    Usage:
        mpid = MPID("NITE")  # OK
        mpid = MPID("nite")  # Normalized to "NITE"
        mpid = MPID("ABCDE") # Raises ValueError - must be 4 chars
    """
    
    __slots__ = ("_value",)
    
    def __init__(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"Expected str, got {type(value).__name__}")
        
        normalized = value.strip().upper()
        
        if len(normalized) != 4:
            raise ValueError(f"MPID must be exactly 4 characters, got '{value}' ({len(normalized)} chars)")
        
        if not normalized.isalnum():
            raise ValueError(f"MPID must be alphanumeric, got '{value}'")
        
        self._value = normalized
    
    @property
    def value(self) -> str:
        return self._value
    
    def __str__(self) -> str:
        return self._value
    
    def __repr__(self) -> str:
        return f"MPID({self._value!r})"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, MPID):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other.upper()
        return False
    
    def __hash__(self) -> int:
        return hash(self._value)


def compute_record_hash(
    week_ending: str,
    tier: str,
    symbol: str,
    mpid: str,
    total_shares: int,
    total_trades: int
) -> str:
    """
    Compute a deterministic hash for a raw OTC record.
    
    Used for:
    - Deduplication during ingestion
    - Linking raw records to normalization results
    
    Hash is based on all significant fields, not just natural key,
    so re-ingesting corrected data creates new records.
    """
    content = f"{week_ending}|{tier}|{symbol}|{mpid}|{total_shares}|{total_trades}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]
```

---

## File: `domains/otc/models.py`

```python
"""
OTC Domain Models

Data classes representing domain entities. These are not ORM models -
they're plain Python objects used to pass data between functions.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .enums import (
    Tier, ManifestStage, NormalizationStatus, QualityStatus,
    QualityCategory, RejectStage, TrendDirection
)
from .validators import WeekEnding, Symbol, MPID


# =============================================================================
# Raw/Ingested Records
# =============================================================================

@dataclass
class RawOTCRecord:
    """
    A record as parsed from FINRA source file.
    
    This is the "bronze" layer - minimally processed, preserving source values.
    """
    week_ending: str          # ISO date string
    tier: str                 # Raw tier string
    symbol: str               # Raw symbol (not normalized)
    mpid: str                 # Raw MPID
    total_shares: int
    total_trades: int
    
    # Source tracking
    source_line_number: int   # 1-based line number in source file
    record_hash: str          # Computed hash for dedup
    
    # Lineage (set during ingestion)
    execution_id: Optional[str] = None
    batch_id: Optional[str] = None


@dataclass
class ParseError:
    """Details about a parsing failure."""
    line_number: int
    raw_line: str
    error_code: str
    error_detail: str


# =============================================================================
# Normalized Records
# =============================================================================

@dataclass
class NormalizedVenueVolume:
    """
    A normalized venue volume record.
    
    This is the "silver" layer - validated, typed, ready for aggregation.
    """
    week_ending: WeekEnding
    tier: Tier
    symbol: Symbol
    mpid: MPID
    total_shares: int
    total_trades: int
    avg_trade_size: Decimal
    
    # Source tracking
    raw_record_hash: str
    
    # Lineage
    execution_id: str
    batch_id: Optional[str] = None


@dataclass
class NormalizationResult:
    """Result of normalizing a raw record."""
    raw_record_hash: str
    status: NormalizationStatus
    normalized: Optional[NormalizedVenueVolume] = None
    reject_reason: Optional[str] = None
    reject_detail: Optional[str] = None


# =============================================================================
# Aggregated Records
# =============================================================================

@dataclass
class SymbolSummary:
    """Per-symbol weekly summary."""
    week_ending: str
    tier: str
    symbol: str
    total_volume: int
    total_trades: int
    venue_count: int
    avg_trade_size: Decimal
    
    calculation_version: str = "v1.0.0"
    execution_id: Optional[str] = None
    batch_id: Optional[str] = None


@dataclass
class VenueShare:
    """Per-venue weekly market share."""
    week_ending: str
    tier: str
    mpid: str
    total_volume: int
    total_trades: int
    market_share_pct: Decimal  # 0-100
    
    calculation_version: str = "v1.0.0"
    execution_id: Optional[str] = None
    batch_id: Optional[str] = None


# =============================================================================
# Rolling Metrics
# =============================================================================

@dataclass
class RollingSymbolMetrics:
    """6-week rolling metrics for a symbol."""
    week_ending: str          # End of the 6-week window
    tier: str
    symbol: str
    
    avg_6w_volume: int
    avg_6w_trades: int
    trend_direction: TrendDirection
    trend_pct: Decimal
    
    weeks_in_window: int      # Actual weeks with data (1-6)
    is_complete_window: bool  # True if weeks_in_window == 6
    
    rolling_version: str = "v1.0.0"
    execution_id: Optional[str] = None
    batch_id: Optional[str] = None


# =============================================================================
# Research Snapshot
# =============================================================================

@dataclass
class ResearchSnapshot:
    """Denormalized research-ready record."""
    week_ending: str
    tier: str
    symbol: str
    
    # Core metrics
    total_volume: int
    total_trades: int
    venue_count: int
    top_venue_mpid: str
    top_venue_share_pct: Decimal
    avg_trade_size: Decimal
    
    # Rolling (may be None if not available)
    rolling_avg_6w_volume: Optional[int]
    rolling_avg_6w_trades: Optional[int]
    rolling_trend_direction: Optional[str]
    rolling_weeks_available: Optional[int]
    rolling_is_complete: Optional[bool]
    
    # Quality
    has_rolling_data: bool
    quality_status: Optional[QualityStatus]
    
    snapshot_version: str = "v1.0.0"
    execution_id: Optional[str] = None
    batch_id: Optional[str] = None


# =============================================================================
# Manifest and Quality
# =============================================================================

@dataclass
class WeekManifest:
    """Manifest entry tracking a week's processing status."""
    week_ending: str
    tier: str
    
    source_type: Optional[str] = None
    source_locator: Optional[str] = None
    source_sha256: Optional[str] = None
    source_bytes: Optional[int] = None
    
    row_count_raw: int = 0
    row_count_parsed: int = 0
    row_count_inserted: int = 0
    row_count_normalized: int = 0
    row_count_rejected: int = 0
    
    stage: ManifestStage = ManifestStage.PENDING
    
    execution_id: Optional[str] = None
    batch_id: Optional[str] = None


@dataclass
class QualityCheck:
    """A quality check result."""
    week_ending: str
    tier: str
    pipeline_name: str
    
    check_name: str
    check_category: QualityCategory
    status: QualityStatus
    
    check_value: Optional[str] = None
    expected_value: Optional[str] = None
    tolerance: Optional[str] = None
    message: Optional[str] = None
    
    execution_id: Optional[str] = None
    batch_id: Optional[str] = None


@dataclass
class Reject:
    """A rejected record."""
    week_ending: Optional[str]
    tier: Optional[str]
    source_locator: str
    line_number: int
    
    raw_line: str
    raw_record_hash: Optional[str]
    
    stage: RejectStage
    reason_code: str
    reason_detail: str
    
    execution_id: str
    batch_id: Optional[str] = None
```

---

## Usage Examples

### Validating Input Parameters

```python
from domains.otc.validators import WeekEnding
from domains.otc.enums import Tier

def ingest_week(params: dict) -> PipelineResult:
    # Validate week_ending is a Friday
    try:
        week = WeekEnding(params["week_ending"])
    except ValueError as e:
        return PipelineResult(status=FAILED, error=str(e))
    
    # Validate tier is known
    try:
        tier = Tier.from_string(params["tier"])
    except ValueError as e:
        return PipelineResult(status=FAILED, error=str(e))
    
    # Now week and tier are guaranteed valid
    ...
```

### Computing Record Hash

```python
from domains.otc.validators import compute_record_hash

hash_val = compute_record_hash(
    week_ending="2025-12-26",
    tier="NMS_TIER_1",
    symbol="AAPL",
    mpid="NITE",
    total_shares=1000000,
    total_trades=5000
)
# hash_val = "a1b2c3d4..."  (32 chars)
```

### Generating Week List for Backfill

```python
from domains.otc.validators import WeekEnding
from datetime import timedelta

def generate_week_list(weeks_back: int) -> list[WeekEnding]:
    """Generate list of WeekEndings from N weeks ago to this week."""
    weeks = []
    for i in range(weeks_back, -1, -1):
        week = WeekEnding.from_weeks_back(i)
        weeks.append(week)
    return weeks

# Example: weeks_back=5 (6 weeks total including current)
# Returns: [WeekEnding("2025-11-28"), ..., WeekEnding("2026-01-03")]
```

---

## Next: Read [03-pipelines-ingest.md](03-pipelines-ingest.md) for ingestion pipeline
