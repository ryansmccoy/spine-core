# OTC Plugin Design Review & Improvement Plan

> **Status:** Design refinement based on architectural review  
> **Audience:** Senior data/platform engineers  
> **Scope:** Cross-tier alignment, domain semantics, operational robustness

---

## 1. Tier-to-Tier Alignment Improvements

### 1.1 Concepts That Should Exist in Basic (Even If Stubbed)

The current designs introduce key concepts too late. For clean tier progression, Basic should establish:

| Concept | Current Tier | Recommended | Rationale |
|---------|--------------|-------------|-----------|
| `batch_id` | Advanced | **Basic** | Every ingestion needs lineage. Even in Basic, "which file did this come from?" |
| `execution_id` | Intermediate | **Basic** | Links pipeline runs to data. Essential for debugging. |
| `record_hash` | Intermediate | **Basic** | Deduplication is fundamental, not a "production" feature. |
| `ingested_at` | All | **All (explicit)** | Must distinguish from `week_ending` and `publication_date`. |
| `source_revision` | None | **All** | FINRA republishes weeks. Track which version we ingested. |

### 1.2 Shared Interfaces Across All Tiers

Define these in Basic, implement progressively:

```python
# market_spine/domains/base.py (should exist in ALL tiers)

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class WeekKey:
    """
    Canonical identifier for a FINRA transparency week.
    
    This is the "logical primary key" across all OTC data.
    """
    tier: str              # "NMS Tier 1" | "NMS Tier 2" | "OTC"
    week_ending: date      # Friday of the reporting week
    
    def __str__(self) -> str:
        return f"{self.tier}:{self.week_ending.isoformat()}"
    
    @classmethod
    def from_string(cls, s: str) -> "WeekKey":
        tier, week_str = s.split(":", 1)
        return cls(tier=tier, week_ending=date.fromisoformat(week_str))


@dataclass(frozen=True)
class RecordKey:
    """
    Primary key for a single FINRA venue-symbol-week record.
    
    This determines deduplication behavior.
    """
    week_ending: date
    tier: str
    symbol: str
    mpid: str
    
    def to_hash(self) -> str:
        """Deterministic 32-char hash for database dedup."""
        import hashlib
        key = f"{self.week_ending.isoformat()}|{self.tier}|{self.symbol}|{self.mpid}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]


class Connector(Protocol):
    """Protocol for data source connectors."""
    
    def fetch(self, week_key: WeekKey) -> bytes:
        """Fetch raw data for a week."""
        ...
    
    def parse(self, raw: bytes, source: str) -> list[dict]:
        """Parse raw bytes into records."""
        ...


class Calculator(Protocol):
    """Protocol for derived calculations."""
    
    name: str
    version: str
    
    def compute(self, inputs: list[dict]) -> list[dict]:
        """Compute derived metrics."""
        ...
    
    def input_weeks_required(self) -> int:
        """How many weeks of history needed (for rolling calcs)."""
        ...
```

### 1.3 Naming Conventions to Freeze Early

Lock these in Basic to prevent refactors:

| Concept | Canonical Name | Never Use |
|---------|----------------|-----------|
| Week identifier | `week_ending` | `lastUpdateDate`, `week_end`, `report_week` |
| Tier values | `"NMS Tier 1"`, `"NMS Tier 2"`, `"OTC"` | `"tier1"`, `"T1"`, `"nms_tier_1"` |
| Venue code | `mpid` | `venue_id`, `market_participant` |
| Symbol | `symbol` | `ticker`, `issueSymbolIdentifier` |
| Hash field | `record_hash` | `hash`, `row_hash`, `dedup_key` |
| Pipeline run | `execution_id` | `run_id`, `job_id`, `pipeline_id` |
| Ingestion group | `batch_id` | `import_id`, `load_id` |

### 1.4 Schema Fields That Should Exist in All Tiers

```sql
-- Raw weekly table (ALL tiers should have these columns)
CREATE TABLE otc_raw_weekly (
    id INTEGER PRIMARY KEY,
    
    -- Identity (exist in Basic, used in all)
    batch_id TEXT NOT NULL,              -- Which ingestion batch
    execution_id TEXT NOT NULL,          -- Which pipeline run
    record_hash TEXT NOT NULL UNIQUE,    -- Deduplication key
    
    -- FINRA data
    week_ending DATE NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    issue_name TEXT,
    venue_name TEXT,
    mpid TEXT NOT NULL,
    share_volume BIGINT NOT NULL,
    trade_count INTEGER NOT NULL,
    
    -- Metadata (exist in Basic, enriched in higher tiers)
    source TEXT NOT NULL,                -- "file", "http", "api"
    source_file TEXT,                    -- Original filename if from file
    source_revision INTEGER DEFAULT 1,   -- FINRA republication version
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## 2. FINRA OTC Domain Semantics (Reality Check)

### 2.1 Date Semantics Clarification

FINRA OTC data has **three distinct dates** that must never be conflated:

| Date | Meaning | Source |
|------|---------|--------|
| `week_ending` | Friday of the trading week reported | `lastUpdateDate` column in file |
| `publication_date` | When FINRA made this data available | Derived from tier + `week_ending` |
| `ingested_at` | When we loaded it into our system | System timestamp |

**Correction needed:** The current design says `lastUpdateDate` is the "Week-ending date (Monday)". FINRA weeks end on **Friday**, not Monday. The `lastUpdateDate` field actually represents the Friday of the reporting week.

### 2.2 Publication Schedule Corrections

```python
# Correct publication delay calculation
from datetime import date, timedelta

def expected_publication_date(week_ending: date, tier: str) -> date:
    """
    Calculate when FINRA should publish this week's data.
    
    Data is published on Wednesday, after the delay period.
    """
    if tier == "NMS Tier 1":
        delay_days = 14  # 2 weeks
    else:  # NMS Tier 2, OTC
        delay_days = 28  # 4 weeks
    
    # Add delay to get target week
    target = week_ending + timedelta(days=delay_days)
    
    # Adjust to Wednesday
    days_until_wed = (2 - target.weekday()) % 7
    return target + timedelta(days=days_until_wed)
```

### 2.3 Handling Revisions (Re-publications)

FINRA occasionally republishes historical weeks to correct errors. Current designs don't address this.

**Recommended approach:**

```python
@dataclass
class IngestionResult:
    """Result of ingesting a week's data."""
    week_key: WeekKey
    record_count: int
    revision: int
    action: str  # "inserted" | "updated" | "skipped"
    previous_revision: int | None


class RevisionPolicy:
    """How to handle re-ingesting existing weeks."""
    
    OVERWRITE = "overwrite"      # Replace all records for the week
    VERSIONED = "versioned"      # Keep old version, add new with higher revision
    SKIP = "skip"                # Don't reingest if week exists
    MERGE = "merge"              # Only insert new records, keep existing


# In repository:
async def ingest_week(
    self,
    week_key: WeekKey,
    records: list[dict],
    revision_policy: str = RevisionPolicy.VERSIONED,
) -> IngestionResult:
    """Ingest records with revision handling."""
    ...
```

### 2.4 Expected vs Unexpected Anomalies

Quality checks should distinguish:

| Anomaly Type | Expected? | Example | Action |
|--------------|-----------|---------|--------|
| Missing week | Sometimes | Holiday weeks, exchange closures | Log, don't alert |
| Zero volume symbol | Yes | Illiquid stocks | Record, don't fail |
| Missing venue | Sometimes | Venue stops operating | Compare to previous week |
| Negative values | **Never** | Data corruption | Reject, alert |
| Future dates | **Never** | File parsing error | Reject, alert |
| Duplicate MPID | **Never** | Data quality issue | Dedupe, log |

```python
@dataclass
class QualityCheckResult:
    """Result of a quality check."""
    check_name: str
    passed: bool
    severity: str  # "info" | "warning" | "error" | "critical"
    is_expected: bool  # Known/acceptable anomaly
    details: dict
```

---

## 3. Idempotency, Deduplication & Replays

### 3.1 Logical Primary Key Definition

The **logical primary key** for a FINRA OTC record is:

```
(week_ending, tier, symbol, mpid)
```

This uniquely identifies one venue's trading activity in one stock for one week.

### 3.2 ID Hierarchy

```
correlation_id      (One business process - e.g., "weekly ingestion run")
    └── execution_id    (One pipeline execution - e.g., "ingest NMS Tier 1")
            └── batch_id        (One atomic write - e.g., "50 records from file X")
                    └── record_hash     (One record's dedup key)
```

**Relationships:**
- `correlation_id`: Groups related pipeline runs (e.g., all three tiers ingested together)
- `execution_id`: Identifies a single pipeline run for debugging/replay
- `batch_id`: Atomic unit for transactional writes
- `record_hash`: Prevents duplicate records across batches

### 3.3 Re-ingestion Scenarios

| Scenario | Behavior | Implementation |
|----------|----------|----------------|
| Same file, same day | Skip (idempotent) | `record_hash` unique constraint |
| Same week, new file | Depends on policy | Check `source_revision` |
| Intentional reprocess | Force flag | `--force` CLI flag bypasses skip |
| Partial failure | Resume | Track `batch_id` completion |
| Backfill old weeks | Normal insert | No special handling needed |

### 3.4 Pipeline Idempotency Pattern

```python
class IdempotentPipeline:
    """Pipeline that can be safely re-run."""
    
    async def run(self, params: dict) -> PipelineResult:
        # 1. Generate deterministic execution key
        logical_key = self.get_logical_key(params)
        
        # 2. Check if already completed
        existing = await self.repo.get_execution(logical_key)
        if existing and existing.status == "completed" and not params.get("force"):
            return PipelineResult(status="skipped", reason="already_completed")
        
        # 3. Lock to prevent concurrent runs
        async with self.lock_manager.acquire(logical_key):
            # 4. Execute with transaction
            async with self.db.transaction() as tx:
                result = await self._execute(params, tx)
                await self.repo.mark_completed(logical_key, result, tx)
        
        return result
```

---

## 4. Calculation & Analytics Plugin Architecture

### 4.1 Calculation Metadata Requirements

Every calculation should declare:

```python
@dataclass
class CalculationSpec:
    """Full specification for a calculation."""
    
    # Identity
    name: str                           # e.g., "symbol_rolling_avg"
    version: str                        # e.g., "v2.1"
    
    # Lineage
    input_tables: list[str]             # ["otc_venue_volume"]
    output_table: str                   # "otc_symbol_rolling_avg"
    
    # Dependencies
    weeks_required: int                 # 6 for rolling average
    depends_on: list[str]               # ["venue_market_share_v1"]
    
    # Behavior
    is_breaking: bool                   # True if output schema changed
    replaces: str | None                # "symbol_rolling_avg_v1" if upgrade
    
    # Documentation
    description: str
    assumptions: list[str]              # ["Volume is non-negative", "MPID is valid"]
    
    # Validation
    output_columns: list[str]
    expected_row_count: str             # "1 per symbol" or "1 per symbol-week"
```

### 4.2 Versioning Strategy

```
calc_name_v{major}.{minor}

v1.0 → v1.1  : Non-breaking (bug fix, optimization)
v1.x → v2.0  : Breaking (schema change, logic change)
```

**Side-by-side execution:**

```python
# Run both versions for comparison
from market_spine.domains.otc.calculations import get_calculation

v1 = get_calculation("symbol_hhi", version="v1")
v2 = get_calculation("symbol_hhi", version="v2")

result_v1 = v1.compute(data, params)
result_v2 = v2.compute(data, params)

# Store both for research comparison
await repo.save_result(result_v1, execution_id, table_suffix="_v1")
await repo.save_result(result_v2, execution_id, table_suffix="_v2")
```

### 4.3 Research-Ready Output

For ML/quant research, calculations should produce:

```sql
-- Every derived table should include:
CREATE TABLE otc_symbol_hhi (
    -- Computation metadata
    execution_id TEXT NOT NULL,
    calc_name TEXT NOT NULL,
    calc_version TEXT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    
    -- Point-in-time keys
    week_ending DATE NOT NULL,
    as_of_date DATE NOT NULL,        -- When this was computed (for backtesting)
    
    -- The actual metrics
    symbol TEXT NOT NULL,
    hhi NUMERIC(8, 2),
    ...
);

-- Index for point-in-time queries
CREATE INDEX idx_hhi_as_of ON otc_symbol_hhi (symbol, as_of_date);
```

---

## 5. Event Sourcing & Projections (Full Tier)

### 5.1 Essential vs Noise Events

**Keep (essential for audit/replay):**
- `FILE_DOWNLOADED` - Source lineage
- `RAW_RECORDS_INGESTED` - Data lineage
- `CALCULATION_COMPLETED` - Derivation lineage
- `QUALITY_GRADE_ASSIGNED` - Data quality audit
- `WEEK_PROCESSING_COMPLETED` - End-to-end tracking

**Collapse/Remove (noise):**
- `FILE_DISCOVERED` - Merge into `FILE_DOWNLOADED`
- `FILE_PARSED` - Merge into `RAW_RECORDS_INGESTED`
- `CALCULATION_STARTED` - Only log if very long-running
- `RECORDS_NORMALIZED` - Merge into `RAW_RECORDS_INGESTED`

### 5.2 Causation Chain Improvements

```python
# Current: flat correlation
event1 = OTCEvent(correlation_id="abc", causation_id=None)
event2 = OTCEvent(correlation_id="abc", causation_id=None)

# Improved: explicit causation tree
download_event = OTCEvent(
    event_id="evt-001",
    event_type="FILE_DOWNLOADED",
    correlation_id="weekly-ingest-2025-12-15",
)

ingest_event = OTCEvent(
    event_id="evt-002",
    event_type="RAW_RECORDS_INGESTED",
    correlation_id="weekly-ingest-2025-12-15",
    causation_id="evt-001",  # Caused by the download
)

calc_event = OTCEvent(
    event_id="evt-003",
    event_type="CALCULATION_COMPLETED",
    correlation_id="weekly-ingest-2025-12-15",
    causation_id="evt-002",  # Caused by the ingestion
)
```

### 5.3 Projection Rebuild Safety

```python
class SafeProjectionRebuilder:
    """Rebuild projections with safety checks."""
    
    async def rebuild(self, projection_name: str) -> None:
        # 1. Create shadow table
        shadow_table = f"{projection_name}_rebuild_{timestamp()}"
        await self.create_table(shadow_table)
        
        # 2. Replay events into shadow
        async for event in self.event_store.stream_all():
            await self.projection.apply(event, table=shadow_table)
        
        # 3. Validate shadow matches expectations
        diff = await self.compare_tables(projection_name, shadow_table)
        if diff.row_count_diff > 100:
            raise ProjectionRebuildError(f"Large diff: {diff}")
        
        # 4. Atomic swap
        async with self.db.transaction():
            await self.rename_table(projection_name, f"{projection_name}_old")
            await self.rename_table(shadow_table, projection_name)
            await self.drop_table(f"{projection_name}_old")
```

---

## 6. Storage & Retention Strategy

### 6.1 Tier Transitions

| Data Volume | Tier | Database | Rationale |
|-------------|------|----------|-----------|
| < 100K rows | Basic | SQLite | Simple, no server |
| 100K - 10M rows | Intermediate | PostgreSQL | Concurrent access, indexes |
| > 10M rows | Advanced | PostgreSQL + S3 | Hot/cold separation |
| Time-series focus | Full | TimescaleDB | Compression, continuous aggregates |

### 6.2 Data Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA LIFECYCLE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────┐    ┌────────────┐    ┌──────────┐    ┌──────────────────────┐ │
│  │  Raw    │───▶│ Normalized │───▶│ Derived  │───▶│ Research-Ready       │ │
│  │ Ingest  │    │   (Clean)  │    │ (Calcs)  │    │ (Point-in-time)      │ │
│  └─────────┘    └────────────┘    └──────────┘    └──────────────────────┘ │
│       │               │                │                    │               │
│       ▼               ▼                ▼                    ▼               │
│   2 years         5 years          5 years              Forever             │
│   (then S3)     (compressed)      (compressed)        (append-only)         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.3 Recommended Retention Policies

```sql
-- TimescaleDB retention policies (Full tier)
SELECT add_retention_policy('otc_raw_weekly', INTERVAL '2 years');
SELECT add_retention_policy('otc_venue_volume', INTERVAL '5 years');
-- Derived tables: no retention (research needs full history)

-- Compression (after 1 month of hot access)
SELECT add_compression_policy('otc_raw_weekly', INTERVAL '1 month');
SELECT add_compression_policy('otc_venue_volume', INTERVAL '1 month');
```

---

## 7. Observability & Operational Guardrails

### 7.1 Data Correctness Metrics (Not Just Infra)

```python
# These matter more than CPU/memory for a data platform

# Ingestion health
otc_weeks_ingested = Counter("otc_weeks_ingested_total", ["tier"])
otc_weeks_missing = Gauge("otc_weeks_missing", ["tier"])
otc_records_per_week = Histogram("otc_records_per_week", ["tier"])

# Data quality
otc_quality_score = Gauge("otc_quality_score", ["tier", "week"])
otc_validation_failures = Counter("otc_validation_failures", ["check_name"])

# Freshness
otc_latest_week = Gauge("otc_latest_week_timestamp", ["tier"])
otc_ingestion_lag_days = Gauge("otc_ingestion_lag_days", ["tier"])

# Consistency
otc_duplicate_records = Counter("otc_duplicate_records_total", ["tier"])
otc_missing_symbols = Gauge("otc_missing_symbols", ["tier"])  # vs previous week
```

### 7.2 Alert Thresholds

| Alert | Threshold | Severity |
|-------|-----------|----------|
| Missing week (Tier 1) | > 3 days past expected | Warning |
| Missing week (Tier 1) | > 7 days past expected | Critical |
| Quality score | < 0.7 | Warning |
| Quality score | < 0.5 | Critical |
| Records per week | < 50% of rolling avg | Warning |
| Pipeline stalled | > 2 hours in "running" | Warning |
| Ingestion lag | > 7 days | Critical |

### 7.3 Dashboard Personas

**Operators Dashboard:**
- Pipeline status (running/failed/completed)
- Ingestion lag by tier
- Error rates
- Resource utilization

**Research Users Dashboard:**
- Data coverage (weeks × tiers matrix)
- Quality grades by week
- Latest available data
- Calculation freshness

---

## 8. Forward-Looking Extensions

### 8.1 Generalized Weekly Transparency Framework

The OTC plugin pattern can generalize to:

```python
# market_spine/domains/transparency/base.py

class WeeklyTransparencyDomain(ABC):
    """Base for any FINRA weekly transparency data."""
    
    domain_name: str  # "otc", "ats", "nms"
    publication_delay_days: dict[str, int]
    tiers: list[str]
    
    @abstractmethod
    def get_connector(self) -> Connector: ...
    
    @abstractmethod
    def get_normalizer(self) -> Normalizer: ...
    
    @abstractmethod
    def get_calculations(self) -> list[Calculator]: ...


# Future domains using same pattern:
class ATSWeeklyDomain(WeeklyTransparencyDomain):
    domain_name = "ats"
    publication_delay_days = {"all": 28}
    tiers = ["ATS"]

class NMSExemptDomain(WeeklyTransparencyDomain):
    domain_name = "nms_exempt"
    ...
```

### 8.2 Point-in-Time Market Microstructure Dataset

For research/backtesting, maintain "as-of" snapshots:

```sql
CREATE TABLE otc_point_in_time (
    symbol TEXT,
    week_ending DATE,
    as_of_date DATE,      -- When we knew this
    
    total_volume BIGINT,
    venue_count INTEGER,
    hhi NUMERIC(8, 2),
    top_venue_share NUMERIC(5, 2),
    
    PRIMARY KEY (symbol, week_ending, as_of_date)
);

-- Query: "What did we know about AAPL on 2025-01-15?"
SELECT * FROM otc_point_in_time
WHERE symbol = 'AAPL'
  AND as_of_date <= '2025-01-15'
ORDER BY week_ending DESC, as_of_date DESC;
```

### 8.3 Feature Store Integration

```python
# Export OTC features for ML pipelines
class OTCFeatureExporter:
    """Export OTC metrics to feature store."""
    
    features = [
        FeatureSpec("venue_concentration_hhi", "float", "6w rolling HHI"),
        FeatureSpec("volume_vs_avg", "float", "Current vs 6w avg %"),
        FeatureSpec("venue_count", "int", "Active venues this week"),
        FeatureSpec("top_venue_share", "float", "Largest venue market share"),
    ]
    
    async def export_to_feast(self, week_ending: date) -> None:
        """Push latest features to Feast feature store."""
        ...
    
    async def export_to_parquet(self, path: Path) -> None:
        """Export for offline training."""
        ...
```

---

## Summary: Key Changes Required

| Document | Priority Changes |
|----------|------------------|
| **Basic** | Add `batch_id`, `execution_id`, `record_hash` to schema. Add `source_revision`. Fix week_ending = Friday. Add shared `WeekKey`, `RecordKey` classes. |
| **Intermediate** | Add revision handling. Improve quality checks (expected vs unexpected). Add `as_of_date` to derived tables. |
| **Advanced** | Add calculation metadata (`input_tables`, `depends_on`, `is_breaking`). Add side-by-side versioning support. |
| **Full** | Collapse noise events. Add causation chain. Add projection rebuild safety. Add point-in-time export. |
| **All** | Consistent naming (`week_ending`, `mpid`, `symbol`). Same core schema fields. Shared base interfaces. |
