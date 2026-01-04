# OTC Data Model

## SQL Tables

### Raw Weekly Data

Stores data exactly as received from FINRA files.

```sql
CREATE TABLE otc.raw_weekly (
    id BIGSERIAL,
    capture_id TEXT NOT NULL,            -- Ingest batch ID (ULID)
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_file TEXT,                     -- Original filename
    
    -- Exact FINRA columns
    tier_description TEXT NOT NULL,       -- "NMS Tier 1" or "NMS Tier 2"
    issue_symbol_identifier TEXT NOT NULL,
    issue_name TEXT,
    market_participant_name TEXT NOT NULL,
    mpid TEXT NOT NULL,                   -- 4-char venue code
    total_weekly_share_quantity BIGINT NOT NULL,
    total_weekly_trade_count INT NOT NULL,
    last_update_date DATE NOT NULL,       -- Week-ending date
    
    raw_checksum TEXT,                    -- SHA256 of source row
    
    PRIMARY KEY (id, ingested_at)
);
```

### Normalized Venue Volume

Cleaned data with derived fields.

```sql
CREATE TABLE otc.venue_volume (
    id BIGSERIAL,
    raw_id BIGINT,                        -- Links to raw_weekly.id
    capture_id TEXT NOT NULL,
    
    week_ending DATE NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,                   -- Stable venue key
    venue_name TEXT,                      -- May change over time
    tier TEXT NOT NULL,                   -- "T1" or "T2"
    
    share_volume BIGINT NOT NULL,
    trade_count INT NOT NULL,
    avg_trade_size NUMERIC(12,2),
    
    normalized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (id, week_ending),
    UNIQUE (week_ending, symbol, mpid, tier)
);
```

### Symbol Weekly Summary

Aggregated across all venues per symbol.

```sql
CREATE TABLE otc.symbol_weekly_summary (
    id BIGSERIAL,
    execution_id TEXT NOT NULL,
    
    week_ending DATE NOT NULL,
    symbol TEXT NOT NULL,
    
    total_volume BIGINT NOT NULL,
    total_trades INT NOT NULL,
    venue_count INT NOT NULL,
    avg_trade_size NUMERIC(12,2),
    
    top_venue TEXT,
    top_venue_volume BIGINT,
    top_venue_pct NUMERIC(5,2),
    
    data_quality_flags JSONB DEFAULT '{}',
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (id, week_ending),
    UNIQUE (week_ending, symbol)
);
```

### Venue Market Share

Per-venue aggregates across all symbols.

```sql
CREATE TABLE otc.venue_market_share (
    id BIGSERIAL,
    execution_id TEXT NOT NULL,
    
    week_ending DATE NOT NULL,
    mpid TEXT NOT NULL,
    
    total_volume BIGINT NOT NULL,
    total_trades INT NOT NULL,
    symbol_count INT NOT NULL,
    
    market_share_pct NUMERIC(5,2),
    rank INT,
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (id, week_ending),
    UNIQUE (week_ending, mpid)
);
```

---

## TimescaleDB Configuration

```sql
-- Partition raw by ingestion time
SELECT create_hypertable('otc.raw_weekly', 'ingested_at',
    chunk_time_interval => INTERVAL '1 month');

-- Partition normalized by week
SELECT create_hypertable('otc.venue_volume', 'week_ending',
    chunk_time_interval => INTERVAL '3 months');

-- Partition summaries by week
SELECT create_hypertable('otc.symbol_weekly_summary', 'week_ending',
    chunk_time_interval => INTERVAL '1 year');
```

---

## Python Models

### Raw Row (from FINRA file)

```python
from datetime import date
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field, computed_field


class NMSTier(str, Enum):
    TIER_1 = "NMS Tier 1"
    TIER_2 = "NMS Tier 2"


class FinraOtcRawRow(BaseModel):
    """Raw row exactly as parsed from FINRA pipe-delimited file."""
    
    tier_description: NMSTier = Field(alias="tierDescription")
    issue_symbol_identifier: str = Field(alias="issueSymbolIdentifier")
    issue_name: str = Field(alias="issueName")
    market_participant_name: str = Field(alias="marketParticipantName")
    mpid: str = Field(alias="MPID", min_length=3, max_length=4)
    total_weekly_share_quantity: int = Field(alias="totalWeeklyShareQuantity", ge=0)
    total_weekly_trade_count: int = Field(alias="totalWeeklyTradeCount", ge=0)
    last_update_date: date = Field(alias="lastUpdateDate")

    model_config = {"populate_by_name": True}

    @computed_field
    @property
    def tier(self) -> str:
        """Normalized tier: 'T1' or 'T2'."""
        return "T1" if self.tier_description == NMSTier.TIER_1 else "T2"
    
    @computed_field
    @property
    def avg_trade_size(self) -> Decimal | None:
        if self.total_weekly_trade_count == 0:
            return None
        return Decimal(self.total_weekly_share_quantity) / Decimal(self.total_weekly_trade_count)
```

### Normalized Models

```python
class VenueVolume(BaseModel):
    """Normalized venue volume for storage."""
    week_ending: date
    symbol: str
    mpid: str
    venue_name: str | None = None
    tier: str
    
    share_volume: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    avg_trade_size: Decimal | None = None
    
    capture_id: str
    raw_id: int | None = None


class SymbolWeeklySummary(BaseModel):
    """Aggregated weekly summary per symbol."""
    week_ending: date
    symbol: str
    
    total_volume: int
    total_trades: int
    venue_count: int
    avg_trade_size: Decimal | None
    
    top_venue_mpid: str
    top_venue_volume: int
    top_venue_pct: Decimal
    
    execution_id: str


class VenueMarketShare(BaseModel):
    """Market share per venue per week."""
    week_ending: date
    mpid: str
    venue_name: str | None = None
    
    total_volume: int
    total_trades: int
    symbol_count: int
    
    market_share_pct: Decimal
    rank: int
    
    execution_id: str
```

---

## File Parser

```python
import csv
from pathlib import Path
from typing import Iterator


def parse_finra_otc_file(file_path: Path) -> Iterator[FinraOtcRawRow]:
    """Parse FINRA OTC weekly transparency file (pipe-delimited)."""
    
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="|")
        
        expected = {
            "tierDescription", "issueSymbolIdentifier", "issueName",
            "marketParticipantName", "MPID", "totalWeeklyShareQuantity",
            "totalWeeklyTradeCount", "lastUpdateDate",
        }
        
        if not reader.fieldnames:
            raise ValueError(f"Empty file: {file_path}")
        
        missing = expected - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        
        for line_num, row in enumerate(reader, start=2):
            try:
                yield FinraOtcRawRow.model_validate(row)
            except Exception as e:
                print(f"Line {line_num}: Failed to parse: {e}")
                continue
```
