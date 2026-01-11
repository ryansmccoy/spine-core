# FINRA OTC Weekly Transparency Data: Complete Processing Guide

> **Purpose:** Comprehensive, implementation-agnostic specification for processing FINRA OTC Weekly Transparency data  
> **Audience:** Engineering teams implementing OTC data pipelines in any system  
> **Last Updated:** 2026-01-02  
> **Version:** 2.0

---

## Table of Contents

1. [What is FINRA OTC Transparency Data?](#1-what-is-finra-otc-transparency-data)
   - 1.1 Overview
   - 1.2 What the Data Contains
   - 1.3 Data Tiers (T1/T2)
   - 1.4 Business Use Cases
   - 1.5 Financial Data Pipeline Philosophy
2. [Data Source Specification](#2-data-source-specification)
   - 2.1 FINRA API Details
   - 2.2 Request Parameters
   - 2.3 File Format Specification
   - 2.4 Field Definitions
   - 2.5 Known ATS Venues (MPIDs)
   - 2.6 Sample Data
3. [Data Model](#3-data-model)
   - 3.1 Core Tables
   - 3.2 TimescaleDB Configuration
   - 3.3 Python Models
   - 3.4 Parsing FINRA Files
4. [Pipeline Stages](#4-pipeline-stages)
   - 4.1 Ingest Stage
   - 4.2 Normalize Stage
   - 4.3 Compute Summary Stage
5. [Key Metrics & Analytics](#5-key-metrics--analysis)
   - 5.1 Venue Market Share Analysis
   - 5.2 Volume Trend Analysis
   - 5.3 Symbol Liquidity Analysis
   - 5.4 Six-Week Rolling Averages
   - 5.5 Venue Rolling Averages
   - 5.6 Concentration Metrics (HHI)
6. [Data Quality Framework](#6-data-quality-framework)
   - 6.1 Quality Dimensions
   - 6.2 Quality Checks
   - 6.3 Quality Metrics Storage
7. [Lineage & Auditability](#7-lineage--auditability)
   - 7.1 Capture ID Tracking
   - 7.2 Execution Linkage
   - 7.3 Point-in-Time Queries
   - 7.5 API Design
8. [Monitoring & Alerting](#8-monitoring--alerting)
9. [Recovery Procedures](#9-recovery-procedures)
10. [Appendix: Schema Reference](#10-appendix-schema-reference)

---

## 1. What is FINRA OTC Transparency Data?

### 1.1 Overview

FINRA (Financial Industry Regulatory Authority) publishes **weekly aggregate trading volume** data for OTC (Over-The-Counter) equities. This data provides transparency into where trading occurs across Alternative Trading Systems (ATSs) and non-ATS OTC venues.

**Critical understanding:**
- This is **NOT trade-level data** — it's pre-aggregated weekly totals
- Each record = one symbol + one venue + one week
- Shows total share volume and trade count for that combination

### 1.2 What the Data Contains

Each record in the weekly publication contains:

| Field | Description | Example |
|-------|-------------|---------|
| `tierDescription` | NMS tier classification | "NMS Tier 1" or "NMS Tier 2" |
| `issueSymbolIdentifier` | Ticker symbol | AAPL, MSFT, AAOI |
| `issueName` | Full security name | "Apple Inc. Common Stock" |
| `marketParticipantName` | ATS venue full name | "SGMT SIGMA X2" |
| `MPID` | 4-character venue code | SGMT, INCR, UBSA |
| `totalWeeklyShareQuantity` | Total shares traded | 15,234,567 |
| `totalWeeklyTradeCount` | Number of trades | 45,230 |
| `lastUpdateDate` | Week-ending date | 2025-12-29 |

### 1.3 Data Tiers

FINRA publishes data in two tiers with different delays:

| Tier | Delay from Week End | Content |
|------|---------------------|---------|
| **Tier 1 (T1)** | 2 weeks | ATS (Alternative Trading System) volume |
| **Tier 2 (T2)** | 4 weeks | Non-ATS OTC volume |

**Example timeline for week ending Friday, January 3, 2026:**
- T1 data available: Wednesday, January 15, 2026
- T2 data available: Wednesday, January 29, 2026

### 1.4 Business Use Cases

| Use Case | Question Answered |
|----------|-------------------|
| **Venue market share** | Which ATSs have the most volume for AAPL? |
| **Liquidity analysis** | Is volume distributed or concentrated? |
| **Best execution** | Where should we route orders? |
| **Trend analysis** | How has venue distribution changed over 6 weeks? |
| **Concentration risk** | Is one venue dominant (regulatory concern)? |
| **Competitive intelligence** | How is our ATS performing vs competitors? |

---

## 1.5 Financial Data Pipeline Philosophy

A production financial data pipeline like Market Spine follows core principles that ensure data integrity, auditability, and reproducibility. This section describes the **ideal approach** that any implementation should follow.

### 1.5.1 The Five Pillars

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FINANCIAL DATA PIPELINE PILLARS                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐       │
│  │ CAPTURE │ → │  STORE  │ → │ QUALITY │ → │ COMPUTE │ → │  SERVE  │       │
│  │         │   │         │   │         │   │         │   │         │       │
│  │ Ingest  │   │ Append- │   │ Validate│   │ Derive  │   │ Query & │       │
│  │ with    │   │ only    │   │ before  │   │ metrics │   │ expose  │       │
│  │ lineage │   │ storage │   │ compute │   │ safely  │   │ via API │       │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘       │
│                                                                             │
│  capture_id    ingested_at   quality_grade execution_id  as-of queries     │
│  checksums     immutable     gate compute   versioned    reproducible      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.5.2 Pillar 1: Capture with Lineage

**Every piece of data must be traceable to its source.**

```python
# Every ingest creates a capture_id that links all downstream data
capture_id = ulid.new().str  # "01HQXYZ..."

# This ID follows the data through the entire pipeline:
# raw_weekly.capture_id → venue_volume.capture_id → referenced in analytics
```

| Requirement | Implementation |
|-------------|----------------|
| Source identification | `capture_id` (ULID) generated at ingest time |
| Timestamp tracking | `ingested_at` records when we received data |
| Content verification | SHA-256 checksum of source file/response |
| Idempotency | Same input → same capture_id (via checksum) |

### 1.5.3 Pillar 2: Append-Only Storage

**Never UPDATE or DELETE stored data. Append new versions instead.**

```sql
-- ❌ WRONG: Updating data destroys history
UPDATE otc.venue_volume SET share_volume = 1000 WHERE id = 123;

-- ✅ RIGHT: Insert new version, mark old as superseded
INSERT INTO otc.venue_volume (..., superseded_at = NULL);
UPDATE otc.venue_volume SET superseded_at = now() WHERE id = 123;
```

**Why append-only?**
- **Reproducibility**: Run the same query at different times, get consistent results
- **Audit trail**: Regulators can see what you knew and when
- **Debugging**: Compare old vs new data to find issues
- **Replay**: Recompute analytics from any point in time

### 1.5.4 Pillar 3: Quality Gates

**Validate before computing. Bad input → no output.**

```python
# Quality check BEFORE computing summaries
quality = await quality_checker.check_week(week_ending)

if quality.grade == 'F':
    raise QualityGateError(f"Cannot compute: {quality.errors}")
elif quality.grade in ('C', 'D'):
    logger.warning(f"Proceeding with warnings: {quality.warnings}")
    # Store warnings in computed metrics for transparency
```

| Gate | Blocks Computation If |
|------|----------------------|
| Schema validation | Missing required columns |
| Completeness | <80% of expected venues |
| Freshness | Data >24h stale |
| Sanity | Volume swings >200% with no explanation |

### 1.5.5 Pillar 4: Versioned Computation

**Every computed metric links to its source data and execution.**

```sql
-- Every metric row knows how it was computed
SELECT 
    m.symbol,
    m.week_ending,
    m.total_volume,
    m.execution_id,      -- Which pipeline run
    e.started_at,        -- When it ran
    e.params,            -- With what parameters
    m.capture_id         -- From which source data
FROM otc.symbol_weekly_summary m
JOIN executions e ON m.execution_id = e.id;
```

### 1.5.6 Pillar 5: As-Of Query Serving

**Every API query should support point-in-time access.**

```http
# What did we know about AAPL on Jan 15, 2026?
GET /api/v1/otc/symbol/AAPL/weekly?week_ending=2025-12-29&as_of=2026-01-15T10:00:00Z

# Current view (default)
GET /api/v1/otc/symbol/AAPL/weekly?week_ending=2025-12-29
```

```sql
-- As-of query implementation
SELECT * FROM otc.venue_volume
WHERE symbol = 'AAPL'
  AND week_ending = '2025-12-29'
  AND ingested_at <= '2026-01-15 10:00:00'::timestamptz
  AND (superseded_at IS NULL OR superseded_at > '2026-01-15 10:00:00'::timestamptz)
ORDER BY ingested_at DESC;
```

---

## 2. Data Source Specification

### 2.1 FINRA API Details

**Base URL:** `https://api.finra.org/data/group/otcMarket/name/weeklySummary`

**Authentication:** Requires FINRA API key (free registration)

**Rate Limits:**
- 10 requests per second
- 10,000 requests per day
- Pagination required for large result sets

### 2.2 Request Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `weekStartDate` | Yes | Monday of the reporting week (YYYY-MM-DD) |
| `tier` | Yes | "T1" or "T2" |
| `limit` | No | Max records per request (default/max: 5000) |
| `offset` | No | Pagination offset |

### 2.3 File Format Specification

**Downloads are pipe-delimited (`|`) text files with header row:**

```
tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 2|AAPL|Apple Inc. Common Stock|SGMT SIGMA X2|SGMT|15234567|45230|2025-12-29
NMS Tier 2|AAPL|Apple Inc. Common Stock|INCR INTELLIGENT CROSS LLC|INCR|12500000|38912|2025-12-29
NMS Tier 1|MSFT|Microsoft Corporation Common Stock|UBSA UBS ATS|UBSA|8234123|22156|2025-12-29
```

**File naming convention:**
- T1: `finra_otc_weekly_tier1.csv` (despite extension, is pipe-delimited)
- T2: `finra_otc_weekly_tier2.csv`
- OTC: `finra_otc_weekly_otc.csv` (non-ATS OTC volume)

### 2.4 Field Definitions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `tierDescription` | STRING | NMS tier classification | "NMS Tier 1", "NMS Tier 2" |
| `issueSymbolIdentifier` | STRING | Ticker symbol | "AAPL", "MSFT", "AAOI" |
| `issueName` | STRING | Full security name | "Apple Inc. Common Stock" |
| `marketParticipantName` | STRING | Full ATS venue name | "SGMT SIGMA X2" |
| `MPID` | STRING(4) | Market Participant ID | "SGMT", "INCR", "UBSA" |
| `totalWeeklyShareQuantity` | INTEGER | Total shares traded | 15234567 |
| `totalWeeklyTradeCount` | INTEGER | Number of trades | 45230 |
| `lastUpdateDate` | DATE | Week-ending date | "2025-12-29" |

**Important notes:**
- `lastUpdateDate` is the **week-ending date**, not when FINRA published
- `MPID` is the stable 4-character venue identifier (use this for joins)
- `marketParticipantName` may change over time (e.g., acquisitions)
- One row = one symbol + one venue + one week

### 2.5 Known ATS Venues (MPIDs)

Common ATSs you'll see in the data:

| MPID | Venue Name | Operator |
|------|------------|----------|
| SGMT | SIGMA X2 | Goldman Sachs |
| INCR | Intelligent Cross | Imperative Execution |
| UBSA | UBS ATS | UBS |
| JPMX | JPM-X | JP Morgan |
| JPBX | JPB-X | JP Morgan |
| MLIX | INSTINCT X | Nomura (Instinet) |
| EBXL | LEVEL ATS | Level ATS |
| LATS | THE BARCLAYS ATS | Barclays |
| MSPL | MS POOL (ATS-4) | Morgan Stanley |
| IATS | IBKR ATS | Interactive Brokers |
| BIDS | BIDS ATS | BIDS Trading |
| CGXS | ONECHRONOS | OneChronos |
| ICBX | CBX | Citigroup |
| KCGM | VIRTU MATCHIT ATS | Virtu |

### 2.6 Sample Data (Actual FINRA Format)

```
tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 2|AAOI|Applied Optoelectronics, Inc. Common Stock|EBXL LEVEL ATS|EBXL|639234|7396|2025-12-29
NMS Tier 2|AAOI|Applied Optoelectronics, Inc. Common Stock|INCR INTELLIGENT CROSS LLC|INCR|526088|8467|2025-12-29
NMS Tier 2|AAOI|Applied Optoelectronics, Inc. Common Stock|UBSA UBS ATS|UBSA|576612|8303|2025-12-29
NMS Tier 2|AAOI|Applied Optoelectronics, Inc. Common Stock|SGMT SIGMA X2|SGMT|290273|4884|2025-12-29
NMS Tier 2|AAOI|Applied Optoelectronics, Inc. Common Stock|MLIX INSTINCT X|MLIX|202106|2027|2025-12-29
```

### 2.7 Known Data Behaviors

| Behavior | Description | Handling |
|----------|-------------|----------|
| **Pipe delimiter** | Files use `|` not `,` | Configure CSV reader accordingly |
| **Empty weeks** | Some symbols have no activity | Absence of record ≠ zero volume |
| **Corrections** | FINRA may republish historical files | Compare checksums on re-fetch |
| **Holiday weeks** | Reduced volume, fewer records | Don't treat as anomaly |
| **Delayed publication** | May be 1-2 days late | Implement retry logic |

---

## 3. Data Model

### 3.1 Core Tables

```sql
-- Raw weekly data exactly as received from FINRA files
CREATE TABLE otc.raw_weekly (
    id BIGSERIAL,
    capture_id TEXT NOT NULL,           -- Links to ingest batch (ULID)
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_file TEXT,                    -- Original filename for audit
    
    -- Exact FINRA columns (verbatim from source)
    tier_description TEXT NOT NULL,      -- "NMS Tier 1" or "NMS Tier 2"
    issue_symbol_identifier TEXT NOT NULL,
    issue_name TEXT,
    market_participant_name TEXT NOT NULL,
    mpid TEXT NOT NULL,                  -- 4-char venue code (SGMT, INCR, etc.)
    total_weekly_share_quantity BIGINT NOT NULL,
    total_weekly_trade_count INT NOT NULL,
    last_update_date DATE NOT NULL,      -- Week-ending date
    
    -- Lineage
    raw_checksum TEXT,                   -- SHA256 of source row
    
    PRIMARY KEY (id, ingested_at)
);

-- Normalized venue volume (cleaned, derived tier)
CREATE TABLE otc.venue_volume (
    id BIGSERIAL,
    raw_id BIGINT,                       -- Links to raw_weekly.id
    capture_id TEXT NOT NULL,
    
    week_ending DATE NOT NULL,           -- From last_update_date
    symbol TEXT NOT NULL,                -- From issue_symbol_identifier
    mpid TEXT NOT NULL,                  -- 4-char venue code (stable key)
    venue_name TEXT,                     -- market_participant_name (may change)
    tier TEXT NOT NULL,                  -- "T1" or "T2" (normalized from tier_description)
    
    share_volume BIGINT NOT NULL,
    trade_count INT NOT NULL,
    avg_trade_size NUMERIC(12,2),        -- share_volume / trade_count
    
    normalized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (id, week_ending),
    UNIQUE (week_ending, symbol, mpid, tier)
);

-- Symbol weekly summary (aggregated across venues)
CREATE TABLE otc.symbol_weekly_summary (
    id BIGSERIAL,
    execution_id TEXT NOT NULL,          -- Pipeline execution that computed this
    
    week_ending DATE NOT NULL,
    symbol TEXT NOT NULL,
    
    total_volume BIGINT NOT NULL,        -- Sum across all venues
    total_trades INT NOT NULL,
    venue_count INT NOT NULL,            -- How many venues reported
    avg_trade_size NUMERIC(12,2),
    
    top_venue TEXT,                      -- Venue with highest volume
    top_venue_volume BIGINT,
    top_venue_pct NUMERIC(5,2),          -- % of total volume
    
    data_quality_flags JSONB DEFAULT '{}',
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (id, week_ending),
    UNIQUE (week_ending, symbol)
);

-- Venue market share (for venue analysis)
CREATE TABLE otc.venue_market_share (
    id BIGSERIAL,
    execution_id TEXT NOT NULL,
    
    week_ending DATE NOT NULL,
    venue_code TEXT NOT NULL,
    
    total_volume BIGINT NOT NULL,        -- Volume across all symbols
    total_trades INT NOT NULL,
    symbol_count INT NOT NULL,           -- How many symbols traded
    
    market_share_pct NUMERIC(5,2),       -- % of total OTC volume
    rank INT,                            -- Rank by volume this week
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (id, week_ending),
    UNIQUE (week_ending, venue_code)
);
```

### 3.2 TimescaleDB Configuration

```sql
-- Partition raw data by ingestion time
SELECT create_hypertable('otc.raw_weekly', 'ingested_at',
    chunk_time_interval => INTERVAL '1 month');

-- Partition normalized data by week
SELECT create_hypertable('otc.venue_volume', 'week_ending',
    chunk_time_interval => INTERVAL '3 months');

-- Partition summaries by week
SELECT create_hypertable('otc.symbol_weekly_summary', 'week_ending',
    chunk_time_interval => INTERVAL '1 year');
```

### 3.3 Python Models

```python
"""Pydantic models for FINRA OTC Weekly Transparency data."""
from datetime import date
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field, computed_field


class NMSTier(str, Enum):
    """NMS tier classification from FINRA."""
    TIER_1 = "NMS Tier 1"
    TIER_2 = "NMS Tier 2"


class FinraOtcRawRow(BaseModel):
    """
    Raw row exactly as parsed from FINRA pipe-delimited file.
    
    Maps directly to FINRA column names.
    """
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
        """Average shares per trade."""
        if self.total_weekly_trade_count == 0:
            return None
        return Decimal(self.total_weekly_share_quantity) / Decimal(self.total_weekly_trade_count)


class VenueVolume(BaseModel):
    """Normalized venue volume record for storage."""
    week_ending: date
    symbol: str
    mpid: str
    venue_name: str | None = None
    tier: str  # "T1" or "T2"
    
    share_volume: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    avg_trade_size: Decimal | None = None
    
    capture_id: str
    raw_id: int | None = None


class SymbolWeeklySummary(BaseModel):
    """Aggregated weekly summary per symbol (across all venues)."""
    week_ending: date
    symbol: str
    
    total_volume: int
    total_trades: int
    venue_count: int
    avg_trade_size: Decimal | None
    
    top_venue_mpid: str
    top_venue_volume: int
    top_venue_pct: Decimal  # 0-100
    
    hhi: Decimal | None = None  # Herfindahl-Hirschman Index
    
    execution_id: str


class VenueMarketShare(BaseModel):
    """Market share metrics per venue per week."""
    week_ending: date
    mpid: str
    venue_name: str | None = None
    
    total_volume: int
    total_trades: int
    symbol_count: int
    
    market_share_pct: Decimal  # 0-100
    rank: int
    
    execution_id: str
```

### 3.4 Parsing FINRA Files

```python
"""Parser for FINRA OTC pipe-delimited files."""
import csv
from pathlib import Path
from typing import Iterator

from .models import FinraOtcRawRow


def parse_finra_otc_file(file_path: Path) -> Iterator[FinraOtcRawRow]:
    """
    Parse FINRA OTC weekly transparency file.
    
    Files are pipe-delimited with header row.
    
    Args:
        file_path: Path to the .csv file (actually pipe-delimited)
        
    Yields:
        FinraOtcRawRow for each valid data row
        
    Raises:
        ValueError: If file format is invalid
    """
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="|")
        
        expected_columns = {
            "tierDescription",
            "issueSymbolIdentifier", 
            "issueName",
            "marketParticipantName",
            "MPID",
            "totalWeeklyShareQuantity",
            "totalWeeklyTradeCount",
            "lastUpdateDate",
        }
        
        if reader.fieldnames is None:
            raise ValueError(f"Empty file: {file_path}")
            
        actual_columns = set(reader.fieldnames)
        missing = expected_columns - actual_columns
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        
        for line_num, row in enumerate(reader, start=2):
            try:
                yield FinraOtcRawRow.model_validate(row)
            except Exception as e:
                # Log and skip invalid rows
                print(f"Line {line_num}: Failed to parse: {e}")
                continue
```

---

## 4. Pipeline Stages

### 4.1 Ingest Stage (`ingest_otc_weekly`)

**Purpose:** Download or load FINRA weekly files, parse, store raw with lineage.

```
Inputs:
  - week_ending: date (the lastUpdateDate in file)
  - tier: str ("T1", "T2", or "OTC")
  - file_path: Path (optional - if already downloaded)

Outputs:
  - capture_id: str (ULID linking all rows from this ingest)
  - record_count: int
  - symbols_count: int
  - venues_count: int (distinct MPIDs)
```

**Data Quality Checks (Pre-Store):**

| Check | Action | Severity |
|-------|--------|----------|
| File exists and readable | FAIL immediately | FAIL |
| Pipe-delimited format | Retry as CSV, then FAIL | FAIL |
| All 8 columns present | FAIL with details | FAIL |
| week_ending matches request | Reject if mismatch >1 day | FAIL |
| Record count reasonable | Warn if T1 <1000 or T2 <5000 | WARN |
| Known MPIDs present | Warn if expected venues missing | WARN |
| Non-empty response | Retry, then FAIL | FAIL |
| Valid CSV parse | Log error, FAIL | FAIL |
| Week ending matches request | Reject if mismatch | FAIL |
| Record count reasonable | Warn if <100 or >10000 | WARN |
| All expected venues present | Warn if missing | WARN |

**Idempotency:**
- Check if `capture_id` exists for this `week_ending` + `published_at`
- If data unchanged (checksum match), skip insert
- If data changed (correction), store new version with new `capture_id`

---

### 4.2 Normalize Stage (`normalize_otc_weekly`)

**Purpose:** Clean and standardize venue names, validate volumes.

```
Inputs:
  - capture_id: str (from ingest)

Outputs:
  - normalized_count: int
  - rejected_count: int
  - venue_mappings_applied: dict
```

**Transformation Rules:**

| Field | Transformation |
|-------|---------------|
| `symbol` | Uppercase, trim whitespace |
| `venue_name` → `venue_code` | Map to standardized codes (see mapping table) |
| `share_volume` | Validate > 0, parse to BIGINT |
| `trade_count` | Validate > 0, parse to INT |
| `avg_trade_size` | Calculate `share_volume / trade_count` |
| `week_ending` | Validate is a Friday |

**Venue Mapping:**

```python
VENUE_MAPPING = {
    # ATS names as reported → standardized code
    "CREDIT SUISSE ATS": "CROS",
    "UBS ATS": "UBSA", 
    "VIRTU AMERICAS ATS": "VIRT",
    "CITADEL SECURITIES ATS": "CITA",
    "JANE STREET ATS": "JANE",
    # ... etc
    
    # For dev/test
    "ATS_A": "ATS_A",
    "ATS_B": "ATS_B",
}
```

**Validation:**

```python
class WeeklyVolumeValidator:
    """Validation for weekly venue volume records."""
    
    def validate(self, record: RawWeeklyRecord) -> ValidationResult:
        errors = []
        warnings = []
        
        # HARD FAILURES
        if not record.symbol:
            errors.append("missing_symbol")
        if record.share_volume is None or record.share_volume < 0:
            errors.append("invalid_volume")
        if record.trade_count is None or record.trade_count < 0:
            errors.append("invalid_trade_count")
        if record.venue_name not in VENUE_MAPPING:
            errors.append("unknown_venue")
        if not self._is_friday(record.week_ending):
            errors.append("week_ending_not_friday")
        
        # SOFT WARNINGS
        if record.share_volume == 0:
            warnings.append("zero_volume")  # Might be valid (suppressed)
        if record.trade_count == 0 and record.share_volume > 0:
            warnings.append("volume_without_trades")  # Data issue
        
        avg_size = record.share_volume / max(record.trade_count, 1)
        if avg_size > 100_000:
            warnings.append("unusually_large_avg_trade")
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
```

---

### 4.3 Compute Summary Stage (`compute_weekly_summary`)

**Purpose:** Aggregate venue volumes into symbol and venue summaries.

```
Inputs:
  - week_ending: date
  - or capture_id: str

Outputs:
  - symbols_computed: int
  - venues_computed: int
```

**Pre-Computation Checks:**

```python
class WeeklySummaryReadinessChecker:
    """Ensure venue data is complete before computing summaries."""
    
    async def check_readiness(self, week_ending: date) -> ReadinessResult:
        
        # 1. Check we have data for this week
        venue_count = await self.db.fetch_val("""
            SELECT COUNT(DISTINCT venue_code) 
            FROM otc.venue_volume
            WHERE week_ending = $1
        """, week_ending)
        
        if venue_count == 0:
            return ReadinessResult(ready=False, reason="no_data_for_week")
        
        # 2. Check minimum venue coverage
        EXPECTED_VENUES = 5  # Configurable
        if venue_count < EXPECTED_VENUES:
            return ReadinessResult(
                ready=True,  # Proceed but warn
                warnings=[f"Only {venue_count} venues, expected {EXPECTED_VENUES}"]
            )
        
        # 3. Check for anomalies in total volume
        total_volume = await self.db.fetch_val("""
            SELECT SUM(share_volume) FROM otc.venue_volume
            WHERE week_ending = $1
        """, week_ending)
        
        # Compare to prior week
        prior_volume = await self.db.fetch_val("""
            SELECT SUM(share_volume) FROM otc.venue_volume
            WHERE week_ending = $1 - INTERVAL '7 days'
        """, week_ending)
        
        if prior_volume and total_volume:
            change_pct = (total_volume - prior_volume) / prior_volume * 100
            if abs(change_pct) > 50:
                return ReadinessResult(
                    ready=True,
                    warnings=[f"Volume changed {change_pct:.1f}% vs prior week"]
                )
        
        return ReadinessResult(ready=True)
```

**Symbol Summary Computation:**

```sql
-- Compute weekly summary per symbol
INSERT INTO otc.symbol_weekly_summary (
    execution_id,
    week_ending,
    symbol,
    total_volume,
    total_trades,
    venue_count,
    avg_trade_size,
    top_venue,
    top_venue_volume,
    top_venue_pct,
    data_quality_flags,
    computed_at
)
SELECT
    $1 as execution_id,
    week_ending,
    symbol,
    
    SUM(share_volume) as total_volume,
    SUM(trade_count) as total_trades,
    COUNT(DISTINCT venue_code) as venue_count,
    SUM(share_volume)::numeric / NULLIF(SUM(trade_count), 0) as avg_trade_size,
    
    -- Top venue by volume
    (ARRAY_AGG(venue_code ORDER BY share_volume DESC))[1] as top_venue,
    MAX(share_volume) as top_venue_volume,
    MAX(share_volume)::numeric / NULLIF(SUM(share_volume), 0) * 100 as top_venue_pct,
    
    $2::jsonb as data_quality_flags,
    now() as computed_at
    
FROM otc.venue_volume
WHERE week_ending = $3
GROUP BY week_ending, symbol;
```

**Venue Market Share Computation:**

```sql
-- Compute market share per venue
WITH venue_totals AS (
    SELECT
        week_ending,
        venue_code,
        SUM(share_volume) as venue_volume,
        SUM(trade_count) as venue_trades,
        COUNT(DISTINCT symbol) as symbol_count
    FROM otc.venue_volume
    WHERE week_ending = $1
    GROUP BY week_ending, venue_code
),
week_total AS (
    SELECT SUM(share_volume) as total FROM venue_totals
)
INSERT INTO otc.venue_market_share (
    execution_id,
    week_ending,
    venue_code,
    total_volume,
    total_trades,
    symbol_count,
    market_share_pct,
    rank,
    computed_at
)
SELECT
    $2 as execution_id,
    v.week_ending,
    v.venue_code,
    v.venue_volume,
    v.venue_trades,
    v.symbol_count,
    v.venue_volume::numeric / NULLIF(w.total, 0) * 100 as market_share_pct,
    RANK() OVER (ORDER BY v.venue_volume DESC) as rank,
    now()
FROM venue_totals v, week_total w;
```

---

## 5. Key Metrics & Analysis

### 5.1 Venue Market Share Analysis

**Question:** Which ATSs have the most volume for a symbol?

```sql
-- Market share by venue for a specific symbol
SELECT 
    v.venue_code,
    v.share_volume,
    v.trade_count,
    v.avg_trade_size,
    v.share_volume::numeric / s.total_volume * 100 as market_share_pct
FROM otc.venue_volume v
JOIN otc.symbol_weekly_summary s 
    ON v.week_ending = s.week_ending AND v.symbol = s.symbol
WHERE v.symbol = 'ALPHA' AND v.week_ending = '2026-01-03'
ORDER BY v.share_volume DESC;
```

**Example output:**
| venue_code | share_volume | trade_count | avg_trade_size | market_share_pct |
|------------|-------------|-------------|----------------|------------------|
| ATS_C | 2,100,000 | 567 | 3,704 | 49.5% |
| ATS_A | 1,250,000 | 342 | 3,655 | 29.5% |
| ATS_B | 890,000 | 198 | 4,495 | 21.0% |

### 5.2 Volume Trend Analysis

**Question:** How has venue distribution changed over time?

```sql
-- 8-week trend of venue market share
SELECT 
    week_ending,
    venue_code,
    market_share_pct,
    rank
FROM otc.venue_market_share
WHERE venue_code IN ('ATS_A', 'ATS_B', 'ATS_C')
ORDER BY week_ending, venue_code;
```

### 5.3 Symbol Liquidity Analysis

**Question:** Which symbols have the most venue coverage?

```sql
-- Symbols with volume across most venues
SELECT 
    symbol,
    total_volume,
    venue_count,
    top_venue,
    top_venue_pct,
    CASE 
        WHEN top_venue_pct > 80 THEN 'concentrated'
        WHEN top_venue_pct > 50 THEN 'moderately_concentrated'
        ELSE 'distributed'
    END as concentration
FROM otc.symbol_weekly_summary
WHERE week_ending = '2026-01-03'
ORDER BY venue_count DESC, total_volume DESC;
```

### 5.4 Six-Week Rolling Averages

**Business requirement:** Smooth out weekly volatility with rolling averages for trend analysis.

**Table for pre-computed rolling averages:**

```sql
CREATE TABLE otc.symbol_rolling_avg (
    id BIGSERIAL,
    execution_id TEXT NOT NULL,
    
    week_ending DATE NOT NULL,
    symbol TEXT NOT NULL,
    
    -- 6-week rolling averages
    avg_6w_volume BIGINT,              -- Avg weekly volume
    avg_6w_trades INT,                 -- Avg weekly trade count
    avg_6w_venue_count NUMERIC(4,1),   -- Avg venues per week
    avg_6w_trade_size NUMERIC(12,2),   -- Avg trade size
    
    -- Trend indicators (current week vs 6-week avg)
    volume_vs_avg_pct NUMERIC(8,2),    -- +/- % from 6w avg
    trend_direction TEXT,              -- 'up', 'down', 'stable'
    
    -- Window metadata
    weeks_in_window INT,               -- Actual weeks available (may be <6 at start)
    earliest_week DATE,
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (id, week_ending),
    UNIQUE (week_ending, symbol)
);
```

**Computation SQL:**

```sql
-- Compute 6-week rolling averages per symbol
WITH rolling_data AS (
    SELECT
        s.week_ending,
        s.symbol,
        s.total_volume,
        s.total_trades,
        s.venue_count,
        s.avg_trade_size,
        
        -- 6-week window
        AVG(s.total_volume) OVER w AS avg_6w_volume,
        AVG(s.total_trades) OVER w AS avg_6w_trades,
        AVG(s.venue_count) OVER w AS avg_6w_venue_count,
        AVG(s.avg_trade_size) OVER w AS avg_6w_trade_size,
        
        COUNT(*) OVER w AS weeks_in_window,
        MIN(s.week_ending) OVER w AS earliest_week
        
    FROM otc.symbol_weekly_summary s
    WINDOW w AS (
        PARTITION BY s.symbol 
        ORDER BY s.week_ending 
        ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
    )
)
INSERT INTO otc.symbol_rolling_avg (
    execution_id, week_ending, symbol,
    avg_6w_volume, avg_6w_trades, avg_6w_venue_count, avg_6w_trade_size,
    volume_vs_avg_pct, trend_direction,
    weeks_in_window, earliest_week
)
SELECT
    $1 as execution_id,
    week_ending,
    symbol,
    
    avg_6w_volume::bigint,
    avg_6w_trades::int,
    ROUND(avg_6w_venue_count, 1),
    ROUND(avg_6w_trade_size, 2),
    
    -- Current vs average
    ROUND((total_volume - avg_6w_volume)::numeric / NULLIF(avg_6w_volume, 0) * 100, 2),
    
    CASE 
        WHEN total_volume > avg_6w_volume * 1.1 THEN 'up'
        WHEN total_volume < avg_6w_volume * 0.9 THEN 'down'
        ELSE 'stable'
    END,
    
    weeks_in_window,
    earliest_week
    
FROM rolling_data
WHERE week_ending = $2;  -- Current week being computed
```

### 5.5 Venue Rolling Averages

**Per-venue rolling averages for market share trend analysis:**

```sql
CREATE TABLE otc.venue_rolling_avg (
    id BIGSERIAL,
    execution_id TEXT NOT NULL,
    
    week_ending DATE NOT NULL,
    mpid TEXT NOT NULL,
    
    -- 6-week rolling averages
    avg_6w_volume BIGINT,
    avg_6w_market_share NUMERIC(5,2),
    avg_6w_symbol_count INT,
    avg_6w_rank NUMERIC(4,1),
    
    -- Trend
    volume_vs_avg_pct NUMERIC(8,2),
    share_vs_avg_pct NUMERIC(5,2),      -- Market share change
    trend_direction TEXT,
    
    weeks_in_window INT,
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (id, week_ending),
    UNIQUE (week_ending, mpid)
);

-- Computation
WITH rolling AS (
    SELECT
        week_ending,
        mpid,
        total_volume,
        market_share_pct,
        symbol_count,
        rank,
        
        AVG(total_volume) OVER w AS avg_6w_volume,
        AVG(market_share_pct) OVER w AS avg_6w_market_share,
        AVG(symbol_count) OVER w AS avg_6w_symbol_count,
        AVG(rank) OVER w AS avg_6w_rank,
        COUNT(*) OVER w AS weeks_in_window
        
    FROM otc.venue_market_share
    WINDOW w AS (
        PARTITION BY mpid
        ORDER BY week_ending
        ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
    )
)
INSERT INTO otc.venue_rolling_avg (...)
SELECT ... FROM rolling WHERE week_ending = $1;
```

### 5.6 Concentration Metrics (HHI)

**Herfindahl-Hirschman Index** measures market concentration:

```sql
-- HHI per symbol (0-10000 scale)
-- <1500 = competitive, 1500-2500 = moderate, >2500 = concentrated
SELECT
    s.week_ending,
    s.symbol,
    SUM(POWER(v.share_volume::numeric / s.total_volume * 100, 2)) as hhi
FROM otc.symbol_weekly_summary s
JOIN otc.venue_volume v ON s.week_ending = v.week_ending AND s.symbol = v.symbol
WHERE s.week_ending = '2025-12-29'
GROUP BY s.week_ending, s.symbol;
```

```python
# Python model for concentration
class SymbolConcentration(BaseModel):
    """Concentration metrics for a symbol."""
    week_ending: date
    symbol: str
    
    hhi: Decimal                    # 0-10000
    concentration_level: str        # 'competitive', 'moderate', 'concentrated'
    top_venue_share: Decimal        # 0-100%
    top_3_venue_share: Decimal      # 0-100%
    
    @computed_field
    @property
    def concentration_level(self) -> str:
        if self.hhi < 1500:
            return "competitive"
        elif self.hhi < 2500:
            return "moderate"
        return "concentrated"
```

---

## 6. Data Quality Framework

### 6.1 Quality Dimensions for Weekly Data

| Dimension | Definition | Measurement |
|-----------|------------|-------------|
| **Completeness** | All expected venues reported | % of known venues with data |
| **Timeliness** | Data published on schedule | Days late from expected publication |
| **Accuracy** | Volumes are plausible | Validation pass rate |
| **Consistency** | Week-over-week changes reasonable | % change vs prior week |
| **Coverage** | Symbols have multiple venues | Avg venues per symbol |

### 6.2 Quality Checks Before Summary Computation

```python
class WeeklyDataQualityChecker:
    """Quality checks specific to OTC weekly transparency data."""
    
    async def check_week(self, week_ending: date) -> QualityResult:
        checks = []
        
        # 1. PUBLICATION TIMELINESS
        # Expected: Wednesday after week ending (Friday)
        expected_publish = week_ending + timedelta(days=5)  # Wednesday
        actual_publish = await self.get_publish_date(week_ending)
        
        if actual_publish > expected_publish + timedelta(days=2):
            checks.append(Warning("late_publication", 
                f"Published {(actual_publish - expected_publish).days} days late"))
        
        # 2. VENUE COVERAGE
        venues_this_week = await self.db.fetch_val("""
            SELECT COUNT(DISTINCT venue_code) FROM otc.venue_volume
            WHERE week_ending = $1
        """, week_ending)
        
        venues_prior_week = await self.db.fetch_val("""
            SELECT COUNT(DISTINCT venue_code) FROM otc.venue_volume
            WHERE week_ending = $1 - INTERVAL '7 days'
        """, week_ending)
        
        if venues_prior_week and venues_this_week < venues_prior_week:
            missing = venues_prior_week - venues_this_week
            checks.append(Warning("missing_venues",
                f"{missing} fewer venues than prior week"))
        
        # 3. VOLUME SANITY CHECK
        # Total volume shouldn't swing >50% week-over-week without explanation
        volume_change = await self.db.fetch_one("""
            WITH this_week AS (
                SELECT SUM(share_volume) as vol FROM otc.venue_volume 
                WHERE week_ending = $1
            ),
            prior_week AS (
                SELECT SUM(share_volume) as vol FROM otc.venue_volume 
                WHERE week_ending = $1 - INTERVAL '7 days'
            )
            SELECT 
                this_week.vol as current,
                prior_week.vol as prior,
                (this_week.vol - prior_week.vol)::float / 
                    NULLIF(prior_week.vol, 0) * 100 as pct_change
            FROM this_week, prior_week
        """, week_ending)
        
        if volume_change and abs(volume_change.pct_change or 0) > 50:
            checks.append(Warning("volume_swing",
                f"Total volume changed {volume_change.pct_change:.1f}% vs prior week"))
        
        # 4. MARKET SHARE STABILITY
        # Check if any venue's market share changed dramatically
        share_changes = await self.db.fetch_all("""
            WITH this_week AS (
                SELECT venue_code, market_share_pct 
                FROM otc.venue_market_share WHERE week_ending = $1
            ),
            prior_week AS (
                SELECT venue_code, market_share_pct 
                FROM otc.venue_market_share WHERE week_ending = $1 - INTERVAL '7 days'
            )
            SELECT 
                t.venue_code,
                t.market_share_pct as current_share,
                p.market_share_pct as prior_share,
                t.market_share_pct - p.market_share_pct as share_change
            FROM this_week t
            JOIN prior_week p ON t.venue_code = p.venue_code
            WHERE ABS(t.market_share_pct - p.market_share_pct) > 10
        """, week_ending)
        
        for change in share_changes:
            checks.append(Warning("market_share_shift",
                f"{change.venue_code} share changed {change.share_change:+.1f}pp"))
        
        # 5. ZERO VOLUME CHECK
        zero_volume_count = await self.db.fetch_val("""
            SELECT COUNT(*) FROM otc.venue_volume
            WHERE week_ending = $1 AND share_volume = 0
        """, week_ending)
        
        if zero_volume_count > 0:
            checks.append(Warning("zero_volume_records",
                f"{zero_volume_count} records with zero volume"))
        
        return QualityResult(
            week_ending=week_ending,
            warnings=checks,
            grade=self._calculate_grade(checks)
        )
    
    def _calculate_grade(self, warnings: list) -> str:
        error_count = len([w for w in warnings if w.severity == 'error'])
        warning_count = len(warnings)
        
        if error_count > 0:
            return 'F'
        elif warning_count == 0:
            return 'A'
        elif warning_count <= 2:
            return 'B'
        elif warning_count <= 5:
            return 'C'
        else:
            return 'D'
```

### 6.3 Quality Metrics Storage

```sql
CREATE TABLE otc.weekly_quality_metrics (
    id BIGSERIAL PRIMARY KEY,
    week_ending DATE NOT NULL UNIQUE,
    measured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Coverage
    venue_count INT,
    symbol_count INT,
    total_records INT,
    
    -- Completeness
    expected_venues INT,
    venue_coverage_pct NUMERIC(5,2),
    
    -- Timeliness
    published_at DATE,
    days_late INT,
    
    -- Consistency
    volume_change_pct NUMERIC(8,2),
    max_share_change_pct NUMERIC(5,2),
    
    -- Validation
    zero_volume_count INT,
    rejected_count INT,
    
    -- Overall
    quality_grade TEXT,  -- A, B, C, D, F
    warnings JSONB
);
```

---

## 7. Lineage & Auditability

### 7.1 Capture ID Tracking

Every row in the pipeline traces back to its source:

```
raw_trades.capture_id ──┐
                        │
normalized_trades ──────┼── capture_id (same)
                        │
daily_metrics ──────────┼── execution_id (links to pipeline run)
                        │
weekly_metrics ─────────┘
```

### 7.2 Execution Linkage

```sql
-- Trace a metric back to its source data
SELECT 
    m.symbol,
    m.trade_date,
    m.vwap,
    e.id as execution_id,
    e.started_at,
    e.completed_at,
    n.capture_id,
    r.ingested_at as source_ingested_at
FROM otc.daily_metrics m
JOIN executions e ON m.execution_id = e.id
JOIN otc.normalized_trades n ON n.symbol = m.symbol AND n.trade_date = m.trade_date
JOIN otc.raw_trades r ON r.capture_id = n.capture_id
WHERE m.symbol = 'ALPHA' AND m.trade_date = '2026-01-02'
LIMIT 10;
```

### 7.3 Point-in-Time Queries

```sql
-- What did we know about ALPHA on 2026-01-02 at 10:00 AM?
SELECT * FROM otc.raw_trades
WHERE symbol = 'ALPHA'
  AND trade_date = '2026-01-02'
  AND ingested_at <= '2026-01-02 10:00:00'::timestamptz
ORDER BY ingested_at DESC;
```

---

## 7.5 API Design

A production financial data pipeline exposes data through well-designed APIs with proper filtering, pagination, and point-in-time support.

### 7.5.1 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/otc/weekly/symbols` | GET | List symbols with OTC data |
| `/api/v1/otc/weekly/symbols/{symbol}` | GET | Weekly data for a symbol |
| `/api/v1/otc/weekly/symbols/{symbol}/venues` | GET | Venue breakdown for symbol |
| `/api/v1/otc/weekly/symbols/{symbol}/rolling` | GET | Rolling averages for symbol |
| `/api/v1/otc/weekly/venues` | GET | List all venues with market share |
| `/api/v1/otc/weekly/venues/{mpid}` | GET | Weekly data for a venue |
| `/api/v1/otc/weekly/venues/{mpid}/symbols` | GET | Symbols traded at venue |
| `/api/v1/otc/quality/{week_ending}` | GET | Quality metrics for a week |
| `/api/v1/otc/ingest/status` | GET | Current ingest pipeline status |

### 7.5.2 Common Query Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `week_ending` | date | Filter by week | `2025-12-29` |
| `week_start` | date | Range start | `2025-11-01` |
| `week_end` | date | Range end | `2025-12-29` |
| `tier` | string | "T1", "T2", or "all" | `T1` |
| `as_of` | datetime | Point-in-time query | `2026-01-15T10:00:00Z` |
| `limit` | int | Pagination limit | `100` |
| `offset` | int | Pagination offset | `0` |
| `sort` | string | Sort field | `total_volume` |
| `order` | string | "asc" or "desc" | `desc` |

### 7.5.3 Response Models

```python
"""API response models for OTC endpoints."""
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class SymbolWeeklyResponse(BaseModel):
    """Weekly OTC summary for a symbol."""
    symbol: str
    week_ending: date
    tier: str
    
    total_volume: int
    total_trades: int
    venue_count: int
    avg_trade_size: Decimal | None
    
    top_venue_mpid: str
    top_venue_name: str | None
    top_venue_share_pct: Decimal
    
    hhi: Decimal | None = None
    concentration_level: str | None = None
    
    # Lineage
    computed_at: datetime
    capture_id: str


class SymbolRollingResponse(BaseModel):
    """Rolling average data for a symbol."""
    symbol: str
    week_ending: date
    
    # Current week
    current_volume: int
    current_trades: int
    
    # 6-week rolling averages
    avg_6w_volume: int
    avg_6w_trades: int
    avg_6w_venue_count: Decimal
    
    # Trend
    volume_vs_avg_pct: Decimal
    trend_direction: str  # 'up', 'down', 'stable'
    weeks_in_window: int


class VenueBreakdownResponse(BaseModel):
    """Volume breakdown by venue for a symbol-week."""
    symbol: str
    week_ending: date
    
    venues: list["VenueVolumeItem"]
    total_volume: int
    
    class VenueVolumeItem(BaseModel):
        mpid: str
        venue_name: str | None
        share_volume: int
        trade_count: int
        market_share_pct: Decimal
        avg_trade_size: Decimal | None


class VenueMarketShareResponse(BaseModel):
    """Market share for a venue."""
    mpid: str
    venue_name: str | None
    week_ending: date
    
    total_volume: int
    total_trades: int
    symbol_count: int
    
    market_share_pct: Decimal
    rank: int
    
    # Rolling
    avg_6w_volume: int | None
    avg_6w_market_share: Decimal | None
    trend_direction: str | None


class PaginatedResponse(BaseModel):
    """Standard paginated response wrapper."""
    data: list
    pagination: "PaginationMeta"
    
    class PaginationMeta(BaseModel):
        total: int
        limit: int
        offset: int
        has_more: bool
```

### 7.5.4 FastAPI Implementation

```python
"""OTC Weekly API endpoints."""
from datetime import date, datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Annotated

from .models import (
    SymbolWeeklyResponse,
    SymbolRollingResponse,
    VenueBreakdownResponse,
    PaginatedResponse,
)
from ..db import Database
from ..auth import get_current_user

router = APIRouter(prefix="/api/v1/otc/weekly", tags=["otc"])


@router.get("/symbols/{symbol}", response_model=SymbolWeeklyResponse)
async def get_symbol_weekly(
    symbol: str,
    week_ending: date = Query(..., description="Week ending date"),
    tier: str = Query("all", regex="^(T1|T2|all)$"),
    as_of: datetime | None = Query(None, description="Point-in-time query"),
    db: Database = Depends(),
) -> SymbolWeeklyResponse:
    """
    Get weekly OTC summary for a symbol.
    
    Returns volume, trade count, venue breakdown, and concentration metrics.
    
    Use `as_of` to query what data was known at a specific point in time.
    """
    query = """
        SELECT 
            s.symbol,
            s.week_ending,
            v.tier,
            s.total_volume,
            s.total_trades,
            s.venue_count,
            s.avg_trade_size,
            s.top_venue as top_venue_mpid,
            s.top_venue_pct as top_venue_share_pct,
            s.computed_at,
            s.capture_id
        FROM otc.symbol_weekly_summary s
        JOIN otc.venue_volume v ON s.symbol = v.symbol AND s.week_ending = v.week_ending
        WHERE s.symbol = $1 
          AND s.week_ending = $2
          AND ($3::text = 'all' OR v.tier = $3)
    """
    
    # Add as-of filtering
    if as_of:
        query += " AND s.computed_at <= $4"
        query += " ORDER BY s.computed_at DESC LIMIT 1"
        row = await db.fetch_one(query, symbol, week_ending, tier, as_of)
    else:
        query += " ORDER BY s.computed_at DESC LIMIT 1"
        row = await db.fetch_one(query, symbol, week_ending, tier)
    
    if not row:
        raise HTTPException(404, f"No data for {symbol} week ending {week_ending}")
    
    return SymbolWeeklyResponse(**row)


@router.get("/symbols/{symbol}/venues", response_model=VenueBreakdownResponse)
async def get_symbol_venues(
    symbol: str,
    week_ending: date = Query(...),
    tier: str = Query("all"),
    db: Database = Depends(),
) -> VenueBreakdownResponse:
    """Get volume breakdown by venue for a symbol."""
    
    rows = await db.fetch_all("""
        SELECT 
            v.mpid,
            v.venue_name,
            v.share_volume,
            v.trade_count,
            v.avg_trade_size,
            v.share_volume::numeric / SUM(v.share_volume) OVER () * 100 as market_share_pct
        FROM otc.venue_volume v
        WHERE v.symbol = $1 
          AND v.week_ending = $2
          AND ($3::text = 'all' OR v.tier = $3)
        ORDER BY v.share_volume DESC
    """, symbol, week_ending, tier)
    
    if not rows:
        raise HTTPException(404, f"No venue data for {symbol}")
    
    return VenueBreakdownResponse(
        symbol=symbol,
        week_ending=week_ending,
        venues=[VenueBreakdownResponse.VenueVolumeItem(**r) for r in rows],
        total_volume=sum(r['share_volume'] for r in rows),
    )


@router.get("/symbols/{symbol}/rolling", response_model=SymbolRollingResponse)
async def get_symbol_rolling(
    symbol: str,
    week_ending: date = Query(...),
    db: Database = Depends(),
) -> SymbolRollingResponse:
    """Get 6-week rolling averages for a symbol."""
    
    row = await db.fetch_one("""
        SELECT 
            r.symbol,
            r.week_ending,
            s.total_volume as current_volume,
            s.total_trades as current_trades,
            r.avg_6w_volume,
            r.avg_6w_trades,
            r.avg_6w_venue_count,
            r.volume_vs_avg_pct,
            r.trend_direction,
            r.weeks_in_window
        FROM otc.symbol_rolling_avg r
        JOIN otc.symbol_weekly_summary s 
            ON r.symbol = s.symbol AND r.week_ending = s.week_ending
        WHERE r.symbol = $1 AND r.week_ending = $2
    """, symbol, week_ending)
    
    if not row:
        raise HTTPException(404, f"No rolling data for {symbol}")
    
    return SymbolRollingResponse(**row)


@router.get("/venues", response_model=PaginatedResponse)
async def list_venues(
    week_ending: date = Query(...),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("total_volume"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    db: Database = Depends(),
) -> PaginatedResponse:
    """List all venues with market share for a week."""
    
    # Validate sort field
    allowed_sorts = {"total_volume", "market_share_pct", "symbol_count", "rank"}
    if sort not in allowed_sorts:
        raise HTTPException(400, f"sort must be one of: {allowed_sorts}")
    
    total = await db.fetch_val("""
        SELECT COUNT(*) FROM otc.venue_market_share WHERE week_ending = $1
    """, week_ending)
    
    rows = await db.fetch_all(f"""
        SELECT 
            m.mpid,
            m.total_volume,
            m.total_trades,
            m.symbol_count,
            m.market_share_pct,
            m.rank,
            r.avg_6w_volume,
            r.avg_6w_market_share,
            r.trend_direction
        FROM otc.venue_market_share m
        LEFT JOIN otc.venue_rolling_avg r 
            ON m.mpid = r.mpid AND m.week_ending = r.week_ending
        WHERE m.week_ending = $1
        ORDER BY m.{sort} {order}
        LIMIT $2 OFFSET $3
    """, week_ending, limit, offset)
    
    return PaginatedResponse(
        data=[VenueMarketShareResponse(**r) for r in rows],
        pagination=PaginatedResponse.PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + len(rows)) < total,
        ),
    )
```

### 7.5.5 API Usage Examples

**Get weekly summary for AAPL:**
```bash
curl "https://api.example.com/api/v1/otc/weekly/symbols/AAPL?week_ending=2025-12-29"
```

**Response:**
```json
{
  "symbol": "AAPL",
  "week_ending": "2025-12-29",
  "tier": "T2",
  "total_volume": 45234567,
  "total_trades": 125430,
  "venue_count": 18,
  "avg_trade_size": 360.65,
  "top_venue_mpid": "INCR",
  "top_venue_name": "INTELLIGENT CROSS LLC",
  "top_venue_share_pct": 23.5,
  "hhi": 1245.67,
  "concentration_level": "competitive",
  "computed_at": "2026-01-15T08:30:00Z",
  "capture_id": "01HQXYZ123ABC"
}
```

**Get venue breakdown:**
```bash
curl "https://api.example.com/api/v1/otc/weekly/symbols/AAOI/venues?week_ending=2025-12-29"
```

**Response:**
```json
{
  "symbol": "AAOI",
  "week_ending": "2025-12-29",
  "total_volume": 4234567,
  "venues": [
    {"mpid": "EBXL", "venue_name": "LEVEL ATS", "share_volume": 639234, "market_share_pct": 15.10},
    {"mpid": "UBSA", "venue_name": "UBS ATS", "share_volume": 576612, "market_share_pct": 13.62},
    {"mpid": "INCR", "venue_name": "INTELLIGENT CROSS LLC", "share_volume": 526088, "market_share_pct": 12.42}
  ]
}
```

**Point-in-time query (what did we know on Jan 15?):**
```bash
curl "https://api.example.com/api/v1/otc/weekly/symbols/AAPL?week_ending=2025-12-29&as_of=2026-01-15T10:00:00Z"
```

---

## 8. Monitoring & Alerting

### 8.1 Key Metrics to Monitor

| Metric | Query | Alert Threshold |
|--------|-------|-----------------|
| Ingest lag | `MAX(now() - ingested_at) WHERE trade_date = today` | > 4 hours |
| Validation failure rate | `rejected / (valid + rejected) * 100` | > 5% |
| Missing symbols | `expected_symbols - COUNT(DISTINCT symbol)` | > 0 |
| Duplicate rate | `duplicates / total * 100` | > 1% |
| Metric computation age | `MAX(now() - computed_at)` | > 1 day |

### 8.2 Daily Quality Report

```sql
-- Generate daily quality summary
SELECT
    trade_date,
    COUNT(DISTINCT symbol) as symbols_with_data,
    SUM(trade_count) as total_trades,
    AVG(validation_pass_rate) as avg_validation_rate,
    COUNT(*) FILTER (WHERE quality_grade = 'A') as grade_a_count,
    COUNT(*) FILTER (WHERE quality_grade IN ('D', 'F')) as poor_quality_count
FROM otc.data_quality_metrics
WHERE metric_date = CURRENT_DATE - INTERVAL '1 day'
GROUP BY trade_date;
```

---

## 9. Recovery Procedures

### 9.1 Reprocess from Raw

```bash
# Reprocess all data for a date range
spine pipeline trigger backfill_range \
  --param start_date=2026-01-01 \
  --param end_date=2026-01-07 \
  --lane backfill
```

### 9.2 Fix Corrupted Metrics

```sql
-- Delete and recompute metrics for a symbol-date
BEGIN;

-- Mark old metrics as superseded
UPDATE otc.daily_metrics
SET superseded_at = now()
WHERE symbol = 'ALPHA' AND trade_date = '2026-01-02';

-- Metrics will be recomputed by pipeline
COMMIT;
```

### 9.3 Backfill Missing Data

```python
# Find and backfill gaps
async def find_and_fill_gaps(symbol: str, start_date: date, end_date: date):
    trading_days = get_trading_calendar(start_date, end_date)
    
    existing = await db.fetch_all("""
        SELECT DISTINCT trade_date FROM otc.daily_metrics
        WHERE symbol = $1 AND trade_date >= $2 AND trade_date <= $3
    """, symbol, start_date, end_date)
    
    existing_dates = {row['trade_date'] for row in existing}
    missing = [d for d in trading_days if d not in existing_dates]
    
    for date in missing:
        await dispatcher.submit(
            pipeline="ingest_otc",
            params={"symbol": symbol, "date": date.isoformat()},
            lane="backfill"
        )
```

---

## 10. Appendix: Schema Reference

### 10.1 Full Table DDL

```sql
-- Raw trades
CREATE TABLE otc.raw_trades (
    id BIGSERIAL,
    capture_id TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    venue TEXT NOT NULL,
    price NUMERIC(18,8),
    quantity BIGINT,
    raw_payload JSONB NOT NULL,
    
    PRIMARY KEY (id, ingested_at)  -- Required for hypertable
);

-- Normalized trades
CREATE TABLE otc.normalized_trades (
    id BIGSERIAL,
    raw_trade_id BIGINT,
    capture_id TEXT NOT NULL,
    source_trade_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    trade_time TIME,
    venue_code TEXT NOT NULL,
    price NUMERIC(18,8) NOT NULL,
    quantity BIGINT NOT NULL,
    notional NUMERIC(18,2) NOT NULL,
    is_cancelled BOOLEAN DEFAULT false,
    is_correction BOOLEAN DEFAULT false,
    validation_warnings JSONB DEFAULT '[]',
    normalized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (id, trade_date),
    UNIQUE (symbol, trade_date, source_trade_id)
);

-- Daily metrics
CREATE TABLE otc.daily_metrics (
    id BIGSERIAL,
    symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    execution_id TEXT NOT NULL,
    
    total_volume BIGINT NOT NULL,
    total_notional NUMERIC(18,2) NOT NULL,
    trade_count INT NOT NULL,
    vwap NUMERIC(18,8),
    
    open_price NUMERIC(18,8),
    high_price NUMERIC(18,8),
    low_price NUMERIC(18,8),
    close_price NUMERIC(18,8),
    
    venue_breakdown JSONB,
    data_quality_flags JSONB DEFAULT '{}',
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ,  -- Set when recomputed
    
    PRIMARY KEY (id, trade_date)
);

CREATE INDEX idx_daily_metrics_symbol_date 
ON otc.daily_metrics(symbol, trade_date DESC)
WHERE superseded_at IS NULL;

-- Rejected trades
CREATE TABLE otc.rejected_trades (
    id BIGSERIAL PRIMARY KEY,
    raw_trade_id BIGINT,
    capture_id TEXT NOT NULL,
    rejection_reason TEXT NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_payload JSONB NOT NULL,
    reviewed_at TIMESTAMPTZ,
    reviewed_by TEXT,
    resolution TEXT  -- 'fixed', 'discarded', 'false_positive'
);
```

---

*This document defines the OTC data pipeline contract. All implementations must adhere to the validation rules and quality gates defined here.*
