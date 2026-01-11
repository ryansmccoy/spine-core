# OTC Shared Models & Schema

> **Purpose:** Common models and SQL that all tiers copy/use  
> **Copy this code** into each tier's `domains/otc/` directory

---

## 1. Shared Python Models

Copy this file to `src/market_spine/domains/otc/models.py` in each tier:

```python
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
    tier: str                    # "NMS Tier 1", "NMS Tier 2", "OTC"
    symbol: str                  # Stock ticker (e.g., "AAPL")
    issue_name: str              # Company name
    venue_name: str              # Full venue name
    mpid: str                    # 4-char venue code
    share_volume: int            # Shares traded
    trade_count: int             # Number of trades
    week_ending: date            # Friday of reporting week
    
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
```

---

## 2. Shared SQL Schema

### 2.1 SQLite Version (Basic)

Copy to `migrations/020_otc_tables.sql`:

```sql
-- migrations/020_otc_tables.sql (SQLite)

-- Raw data from FINRA files
CREATE TABLE IF NOT EXISTS otc_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    record_hash TEXT NOT NULL UNIQUE,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    issue_name TEXT,
    venue_name TEXT,
    mpid TEXT NOT NULL,
    share_volume INTEGER NOT NULL,
    trade_count INTEGER NOT NULL,
    
    source_file TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_otc_raw_week ON otc_raw(week_ending);
CREATE INDEX IF NOT EXISTS idx_otc_raw_symbol ON otc_raw(symbol);


-- Normalized venue volumes
CREATE TABLE IF NOT EXISTS otc_venue_volume (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    share_volume INTEGER NOT NULL,
    trade_count INTEGER NOT NULL,
    avg_trade_size TEXT,
    record_hash TEXT NOT NULL,
    
    normalized_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid)
);

CREATE INDEX IF NOT EXISTS idx_venue_week ON otc_venue_volume(week_ending);
CREATE INDEX IF NOT EXISTS idx_venue_symbol ON otc_venue_volume(symbol);


-- Symbol weekly summaries
CREATE TABLE IF NOT EXISTS otc_symbol_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,
    avg_trade_size TEXT,
    
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol)
);


-- Venue market share
CREATE TABLE IF NOT EXISTS otc_venue_share (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    week_ending TEXT NOT NULL,
    mpid TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    symbol_count INTEGER NOT NULL,
    market_share_pct TEXT NOT NULL,
    rank INTEGER NOT NULL,
    
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, mpid)
);
```

### 2.2 PostgreSQL Version (Intermediate, Advanced)

Copy to `migrations/020_otc_tables.sql`:

```sql
-- migrations/020_otc_tables.sql (PostgreSQL)

CREATE SCHEMA IF NOT EXISTS otc;

-- Raw data from FINRA files
CREATE TABLE otc.raw (
    id BIGSERIAL PRIMARY KEY,
    batch_id TEXT NOT NULL,
    record_hash TEXT NOT NULL UNIQUE,
    
    week_ending DATE NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    issue_name TEXT,
    venue_name TEXT,
    mpid TEXT NOT NULL,
    share_volume BIGINT NOT NULL,
    trade_count INTEGER NOT NULL,
    
    source_file TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_otc_raw_week ON otc.raw(week_ending);
CREATE INDEX idx_otc_raw_symbol ON otc.raw(symbol);


-- Normalized venue volumes
CREATE TABLE otc.venue_volume (
    id BIGSERIAL PRIMARY KEY,
    
    week_ending DATE NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    share_volume BIGINT NOT NULL,
    trade_count INTEGER NOT NULL,
    avg_trade_size NUMERIC(18, 4),
    record_hash TEXT NOT NULL,
    
    normalized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(week_ending, tier, symbol, mpid)
);

CREATE INDEX idx_venue_week ON otc.venue_volume(week_ending);
CREATE INDEX idx_venue_symbol ON otc.venue_volume(symbol);


-- Symbol weekly summaries
CREATE TABLE otc.symbol_summary (
    id BIGSERIAL PRIMARY KEY,
    
    week_ending DATE NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    total_volume BIGINT NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,
    avg_trade_size NUMERIC(18, 4),
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(week_ending, tier, symbol)
);


-- Venue market share
CREATE TABLE otc.venue_share (
    id BIGSERIAL PRIMARY KEY,
    
    week_ending DATE NOT NULL,
    mpid TEXT NOT NULL,
    total_volume BIGINT NOT NULL,
    total_trades INTEGER NOT NULL,
    symbol_count INTEGER NOT NULL,
    market_share_pct NUMERIC(5, 2) NOT NULL,
    rank INTEGER NOT NULL,
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(week_ending, mpid)
);
```

---

## 3. Shared Parsing Logic

Copy to `src/market_spine/domains/otc/parser.py`:

```python
# src/market_spine/domains/otc/parser.py

"""
FINRA file parsing - shared across all tiers.

Copy this file directly to each project.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterator

from market_spine.domains.otc.models import RawRecord


def parse_finra_file(file_path: Path) -> Iterator[RawRecord]:
    """
    Parse a FINRA OTC weekly transparency file.
    
    Expects pipe-delimited CSV with headers:
    - tierDescription
    - issueSymbolIdentifier
    - issueName
    - marketParticipantName
    - MPID
    - totalWeeklyShareQuantity
    - totalWeeklyTradeCount
    - lastUpdateDate
    
    Yields RawRecord for each valid row.
    """
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="|")
        
        for row in reader:
            try:
                yield RawRecord(
                    tier=row["tierDescription"],
                    symbol=row["issueSymbolIdentifier"].upper().strip(),
                    issue_name=row["issueName"],
                    venue_name=row["marketParticipantName"],
                    mpid=row["MPID"].upper().strip(),
                    share_volume=int(row["totalWeeklyShareQuantity"]),
                    trade_count=int(row["totalWeeklyTradeCount"]),
                    week_ending=datetime.strptime(
                        row["lastUpdateDate"], "%Y-%m-%d"
                    ).date(),
                )
            except (ValueError, KeyError):
                continue  # Skip malformed rows


def parse_finra_content(content: str) -> Iterator[RawRecord]:
    """Parse FINRA data from string content (for HTTP downloads)."""
    import io
    reader = csv.DictReader(io.StringIO(content), delimiter="|")
    
    for row in reader:
        try:
            yield RawRecord(
                tier=row["tierDescription"],
                symbol=row["issueSymbolIdentifier"].upper().strip(),
                issue_name=row["issueName"],
                venue_name=row["marketParticipantName"],
                mpid=row["MPID"].upper().strip(),
                share_volume=int(row["totalWeeklyShareQuantity"]),
                trade_count=int(row["totalWeeklyTradeCount"]),
                week_ending=datetime.strptime(
                    row["lastUpdateDate"], "%Y-%m-%d"
                ).date(),
            )
        except (ValueError, KeyError):
            continue
```

---

## 4. Shared Normalization Logic

Copy to `src/market_spine/domains/otc/normalizer.py`:

```python
# src/market_spine/domains/otc/normalizer.py

"""
Normalization logic - shared across all tiers.

Copy this file directly to each project.
"""

from decimal import Decimal

from market_spine.domains.otc.models import (
    RawRecord,
    VenueVolume,
    NormalizeResult,
    Tier,
)


def normalize_records(records: list[RawRecord]) -> NormalizeResult:
    """
    Normalize raw FINRA records into VenueVolume records.
    
    Transformations:
    - Parse tier string to enum
    - Calculate avg trade size
    - Skip records with negative values
    """
    accepted = []
    rejected = 0
    
    for raw in records:
        # Validate
        if raw.share_volume < 0 or raw.trade_count < 0:
            rejected += 1
            continue
        
        # Parse tier
        try:
            tier = Tier.from_finra(raw.tier)
        except ValueError:
            rejected += 1
            continue
        
        # Calculate avg trade size
        avg_size = None
        if raw.trade_count > 0:
            avg_size = Decimal(raw.share_volume) / Decimal(raw.trade_count)
        
        accepted.append(VenueVolume(
            week_ending=raw.week_ending,
            tier=tier,
            symbol=raw.symbol,
            mpid=raw.mpid,
            share_volume=raw.share_volume,
            trade_count=raw.trade_count,
            avg_trade_size=avg_size,
            record_hash=raw.record_hash,
        ))
    
    return NormalizeResult(
        processed=len(records),
        accepted=len(accepted),
        rejected=rejected,
        records=accepted,
    )
```

---

## 5. Shared Calculation Logic

Copy to `src/market_spine/domains/otc/calculations.py`:

```python
# src/market_spine/domains/otc/calculations.py

"""
Aggregation calculations - shared across all tiers.

Copy this file directly to each project.
"""

from collections import defaultdict
from decimal import Decimal

from market_spine.domains.otc.models import (
    VenueVolume,
    SymbolSummary,
    VenueShare,
)


def compute_symbol_summaries(venue_data: list[VenueVolume]) -> list[SymbolSummary]:
    """
    Aggregate venue data to symbol summaries.
    
    Groups by (week, tier, symbol) and sums volumes.
    """
    groups: dict[tuple, list[VenueVolume]] = defaultdict(list)
    
    for v in venue_data:
        key = (v.week_ending, v.tier, v.symbol)
        groups[key].append(v)
    
    summaries = []
    for (week, tier, symbol), venues in groups.items():
        total_vol = sum(v.share_volume for v in venues)
        total_trades = sum(v.trade_count for v in venues)
        
        avg_size = None
        if total_trades > 0:
            avg_size = Decimal(total_vol) / Decimal(total_trades)
        
        summaries.append(SymbolSummary(
            week_ending=week,
            tier=tier,
            symbol=symbol,
            total_volume=total_vol,
            total_trades=total_trades,
            venue_count=len(venues),
            avg_trade_size=avg_size,
        ))
    
    return summaries


def compute_venue_shares(venue_data: list[VenueVolume]) -> list[VenueShare]:
    """
    Compute venue market share across all symbols.
    
    Groups by (week, mpid) and calculates % of total.
    """
    # Calculate weekly totals
    week_totals: dict = defaultdict(int)
    for v in venue_data:
        week_totals[v.week_ending] += v.share_volume
    
    # Group by (week, mpid)
    groups: dict[tuple, list[VenueVolume]] = defaultdict(list)
    for v in venue_data:
        groups[(v.week_ending, v.mpid)].append(v)
    
    results = []
    for (week, mpid), venues in groups.items():
        total_vol = sum(v.share_volume for v in venues)
        total_trades = sum(v.trade_count for v in venues)
        symbols = {v.symbol for v in venues}
        
        week_total = week_totals[week]
        share_pct = Decimal(0)
        if week_total > 0:
            share_pct = (Decimal(total_vol) / Decimal(week_total) * 100).quantize(Decimal("0.01"))
        
        results.append(VenueShare(
            week_ending=week,
            mpid=mpid,
            total_volume=total_vol,
            total_trades=total_trades,
            symbol_count=len(symbols),
            market_share_pct=share_pct,
        ))
    
    # Rank by volume per week
    by_week: dict = defaultdict(list)
    for r in results:
        by_week[r.week_ending].append(r)
    
    for week, venues in by_week.items():
        venues.sort(key=lambda v: v.total_volume, reverse=True)
        for i, v in enumerate(venues, 1):
            v.rank = i
    
    return results
```

---

## 6. Tier Progression Summary

| File | Basic | Intermediate | Advanced | Full |
|------|-------|--------------|----------|------|
| `models.py` | ✅ Copy | ✅ Copy | ✅ Copy | ✅ Copy |
| `parser.py` | ✅ Copy | ✅ Copy | ✅ Copy | ✅ Copy |
| `normalizer.py` | ✅ Copy | ✅ Copy | ✅ Copy | ✅ Copy |
| `calculations.py` | ✅ Copy | ✅ Copy | ✅ Copy | ✅ Copy |
| `020_otc_tables.sql` | SQLite | PostgreSQL | PostgreSQL | TimescaleDB |
| `connector.py` | File only | + HTTP | + Retry | + S3 cache |
| `repository.py` | — | ✅ Add | ✅ Add | ✅ Add |
| `quality.py` | — | ✅ Add | ✅ Add | ✅ Add |
| `pipelines.py` | Simple | + Async | + Celery | + Events |

**Key principle:** Core data models and logic are **copied** to each project. 
Tier-specific features are **added** as you progress up.
