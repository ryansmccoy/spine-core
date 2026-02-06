# Refactor Plan: Platform Primitives → spine.core

> **Goal**: Thin OTC domain, thick platform. Make domain code portable across Basic/Intermediate/Advanced/Full tiers.

---

## Executive Summary

The current OTC multi-week implementation is **functionally correct** but **structurally heavy**. ~80% of the code is reusable platform machinery, not OTC-specific logic.

**Before**: 6 pipeline files × 300+ lines = ~1800 lines of OTC code  
**After**: 5 domain files × ~100 lines = ~500 lines of OTC code + ~1000 lines shared in `spine.core`

---

## 1. Classification: Platform Primitive vs Domain-Specific

### Platform Primitives (Move to `spine.core`)

| Concept | Current Location | Move To | Reusable By |
|---------|------------------|---------|-------------|
| `WeekEnding` validation | `otc/validators.py` | `spine.core.temporal` | Any weekly domain |
| `WeekRange` generation | `backfill_range.py` | `spine.core.temporal` | Any backfill |
| Execution context (execution_id, batch_id) | Inline in pipelines | `spine.core.execution` | All pipelines |
| Idempotency checks (already done?) | Inline in pipelines | `spine.core.idempotency` | All pipelines |
| Delete+Insert pattern | Inline in pipelines | `spine.core.idempotency` | Level 3 pipelines |
| Work manifest (stage tracking) | `otc_week_manifest` SQL | `spine.core.manifest` | Any multi-stage workflow |
| Reject sink (write rejects) | Inline SQL | `spine.core.rejects` | Any validation |
| Quality check runner | `quality_checks.py` | `spine.core.quality` | Any domain |
| Rolling window helper | `compute_rolling.py` | `spine.core.rolling` | Any time-series |
| Snapshot builder pattern | `research_snapshot.py` | `spine.core.snapshot` | Any denormalized output |
| Record hashing | `validators.py` | `spine.core.hashing` | Any dedup |

### Domain-Specific (Keep in `domains/otc`)

| Concept | Why OTC-Specific |
|---------|------------------|
| FINRA PSV file format | Column names, delimiter, header detection |
| Tier enum (NMS_TIER_1, etc.) | FINRA-specific classification |
| Symbol/MPID validation rules | FINRA format (4-char MPID, etc.) |
| Natural key (week,tier,symbol,mpid) | OTC-specific composite key |
| Market share calculation | Business rule: volume/total*100 |
| Trend thresholds (±5%) | OTC-specific magic number |
| OTC table names | `otc_raw`, `otc_venue_volume`, etc. |

---

## 2. New File Tree

### `spine.core` Package (Platform Primitives)

```
src/spine/core/
├── __init__.py
├── temporal.py              # WeekEnding, WeekRange, date bucket utils
├── execution.py             # ExecutionContext dataclass, context propagation
├── idempotency.py           # IdempotencyChecker, DeleteInsertHelper
├── manifest.py              # WorkManifest protocol, stage tracking
├── rejects.py               # RejectSink, RejectReason enum skeleton
├── quality.py               # QualityRunner, QualityCheck, QualityStatus
├── rolling.py               # RollingWindow helper (generic N-period)
├── snapshot.py              # SnapshotBuilder protocol
├── hashing.py               # record_hash helper
├── storage.py               # Connection protocol (SQLite/Postgres agnostic)
└── pipeline.py              # Existing Pipeline base class
```

### `domains/otc` Package (Thin Domain)

```
src/spine/domains/otc/
├── __init__.py              # Just imports
├── schema.py                # Table names, natural key, tier enum
├── connector.py             # Parse FINRA PSV → RawOTCRecord
├── normalizer.py            # RawOTCRecord → VenueVolume + validation
├── calculations.py          # Pure functions: aggregate, share, trend
└── pipelines.py             # Thin orchestration (single file!)
```

**6 files total for OTC domain** (vs 12+ currently documented).

---

## 3. Core Module Specifications

### `spine.core.temporal`

```python
"""Temporal primitives for weekly/monthly/quarterly workflows."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterator

@dataclass(frozen=True)
class WeekEnding:
    """Validated Friday date for weekly workflows."""
    value: date
    
    def __init__(self, value: date | str):
        # Validate is Friday, parse if string
        ...
    
    @classmethod
    def from_any_date(cls, d: date) -> "WeekEnding":
        """Find containing week's Friday."""
        ...
    
    @classmethod  
    def range(cls, start: "WeekEnding", end: "WeekEnding") -> Iterator["WeekEnding"]:
        """Generate all Fridays in range (inclusive)."""
        ...
    
    @classmethod
    def last_n(cls, n: int, as_of: date = None) -> list["WeekEnding"]:
        """Get last N week endings including as_of date's week."""
        ...


@dataclass(frozen=True)
class MonthEnding:
    """Validated month-end date for monthly workflows."""
    value: date
    # Similar API for monthly domains
```

### `spine.core.execution`

```python
"""Execution context for lineage tracking."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid

@dataclass
class ExecutionContext:
    """Context passed through pipeline execution for lineage."""
    
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    batch_id: Optional[str] = None
    parent_execution_id: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    
    def child(self) -> "ExecutionContext":
        """Create child context for sub-pipeline."""
        return ExecutionContext(
            batch_id=self.batch_id,
            parent_execution_id=self.execution_id
        )


def with_execution_context(batch_id: str = None) -> ExecutionContext:
    """Create new execution context, optionally with batch_id."""
    return ExecutionContext(batch_id=batch_id)
```

### `spine.core.idempotency`

```python
"""Idempotency helpers for pipeline stages."""

from typing import Protocol, Any
from enum import IntEnum

class IdempotencyLevel(IntEnum):
    """Pipeline idempotency levels."""
    L1_APPEND_ONLY = 1      # Always inserts, caller dedupes
    L2_INPUT_IDEMPOTENT = 2 # Same input → same output (hash dedup)
    L3_STATE_IDEMPOTENT = 3 # Re-run → DELETE+INSERT → same state

class IdempotencyChecker:
    """Check if work already done for a logical key."""
    
    def __init__(self, conn, table: str, key_columns: list[str], stage_column: str = None):
        self.conn = conn
        self.table = table
        self.key_columns = key_columns
        self.stage_column = stage_column
    
    def is_complete(self, key_values: dict, min_stage: str = None) -> bool:
        """Check if logical key already processed."""
        ...
    
    def delete_and_insert(self, key_values: dict, records: list[dict]):
        """Delete existing, insert new (Level 3 pattern)."""
        ...
```

### `spine.core.manifest`

```python
"""Generic work manifest for tracking multi-stage workflows."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any
from enum import Enum

class ManifestProtocol:
    """Protocol for domain-specific manifest tables."""
    
    def get_stage(self, key: dict) -> Optional[str]:
        """Get current stage for work item."""
        ...
    
    def update_stage(self, key: dict, stage: str, metrics: dict = None):
        """Update stage and optional metrics."""
        ...
    
    def create_if_missing(self, key: dict, initial_stage: str):
        """Create manifest entry if not exists."""
        ...


class WorkManifest(ManifestProtocol):
    """Generic implementation backed by any manifest table."""
    
    def __init__(
        self, 
        conn, 
        table: str,
        key_columns: list[str],
        stage_column: str = "stage",
        metrics_columns: list[str] = None
    ):
        self.conn = conn
        self.table = table
        self.key_columns = key_columns
        self.stage_column = stage_column
        self.metrics_columns = metrics_columns or []
```

### `spine.core.rejects`

```python
"""Standardized reject handling."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any
from enum import Enum

@dataclass
class Reject:
    """A rejected record."""
    stage: str              # INGEST | NORMALIZE | AGGREGATE
    reason_code: str        # Machine-readable (INVALID_SYMBOL, etc)
    reason_detail: str      # Human-readable
    raw_data: Any           # Original record/line
    source_locator: str = None
    line_number: int = None

class RejectSink:
    """Write rejects to storage."""
    
    def __init__(self, conn, table: str, execution_context):
        self.conn = conn
        self.table = table
        self.ctx = execution_context
    
    def write(self, reject: Reject, domain_key: dict = None):
        """Write single reject with lineage."""
        ...
    
    def write_batch(self, rejects: list[Reject], domain_key: dict = None):
        """Write multiple rejects efficiently."""
        ...
```

### `spine.core.quality`

```python
"""Quality check framework."""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Any

class QualityStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"

class QualityCategory(str, Enum):
    INTEGRITY = "INTEGRITY"
    COMPLETENESS = "COMPLETENESS"
    BUSINESS_RULE = "BUSINESS_RULE"

@dataclass
class QualityCheck:
    """Definition of a quality check."""
    name: str
    category: QualityCategory
    check_fn: Callable[[Any], tuple[QualityStatus, str]]  # Returns (status, message)

class QualityRunner:
    """Run quality checks and record results."""
    
    def __init__(self, conn, table: str, execution_context):
        self.conn = conn
        self.table = table
        self.ctx = execution_context
        self.checks: list[QualityCheck] = []
    
    def add_check(self, check: QualityCheck):
        """Register a check to run."""
        self.checks.append(check)
    
    def run_all(self, context: dict) -> dict[str, QualityStatus]:
        """Run all checks, record results, return summary."""
        ...
```

### `spine.core.rolling`

```python
"""Rolling window utilities for time-series calculations."""

from dataclasses import dataclass
from typing import TypeVar, Generic, Callable, Iterator
from datetime import date

T = TypeVar("T")  # The time bucket type (WeekEnding, MonthEnding, date)
V = TypeVar("V")  # The value type

@dataclass
class RollingWindow(Generic[T, V]):
    """Generic rolling window over time buckets."""
    
    window_size: int  # Number of periods
    bucket_type: type[T]  # WeekEnding, MonthEnding, etc
    
    def compute(
        self,
        as_of: T,
        fetch_fn: Callable[[T], V | None],
        aggregate_fn: Callable[[list[tuple[T, V]]], dict]
    ) -> dict:
        """
        Compute rolling aggregate.
        
        Args:
            as_of: The "current" bucket
            fetch_fn: Get value for a bucket (may return None for missing)
            aggregate_fn: Combine values into result dict
            
        Returns:
            Dict with aggregates + metadata (periods_present, is_complete)
        """
        buckets = self._get_window_buckets(as_of)
        values = [(b, fetch_fn(b)) for b in buckets]
        present = [(b, v) for b, v in values if v is not None]
        
        result = aggregate_fn(present)
        result["periods_in_window"] = len(present)
        result["is_complete_window"] = len(present) == self.window_size
        return result
```

### `spine.core.storage`

```python
"""Database-agnostic storage protocol."""

from typing import Protocol, Any, Iterator
from contextlib import contextmanager

class Connection(Protocol):
    """Minimal connection interface (works with sqlite3, psycopg, etc)."""
    
    def execute(self, sql: str, params: tuple = ()) -> Any: ...
    def executemany(self, sql: str, params: list[tuple]) -> Any: ...
    def commit(self) -> None: ...

class StorageBackend(Protocol):
    """Abstract storage for domain data."""
    
    @contextmanager
    def transaction(self) -> Iterator[Connection]: ...
    
    def get_connection(self) -> Connection: ...
```

---

## 4. Thin OTC Domain (After Refactor)

### `domains/otc/schema.py`

```python
"""OTC domain constants and schema definitions."""

from enum import Enum

class Tier(str, Enum):
    NMS_TIER_1 = "NMS_TIER_1"
    NMS_TIER_2 = "NMS_TIER_2"
    OTC = "OTC"

# Table names
TABLES = {
    "raw": "otc_raw",
    "venue_volume": "otc_venue_volume",
    "symbol_summary": "otc_symbol_summary",
    "venue_share": "otc_venue_share",
    "rolling": "otc_symbol_rolling_6w",
    "snapshot": "otc_research_snapshot",
    "manifest": "otc_week_manifest",
    "rejects": "otc_rejects",
    "quality": "otc_quality_checks",
}

# Natural key for OTC data
NATURAL_KEY = ["week_ending", "tier", "symbol", "mpid"]

# Manifest stages (domain uses generic core.manifest)
STAGES = ["PENDING", "INGESTED", "NORMALIZED", "AGGREGATED", "ROLLING", "SNAPSHOT"]
```

### `domains/otc/connector.py`

```python
"""Parse FINRA OTC PSV files."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
import hashlib

@dataclass
class RawOTCRecord:
    """Record as parsed from FINRA file (bronze layer)."""
    week_ending: str
    tier: str
    symbol: str
    mpid: str
    total_shares: int
    total_trades: int
    source_line: int
    record_hash: str

def parse_finra_file(path: Path) -> Iterator[RawOTCRecord]:
    """Parse FINRA PSV file into raw records."""
    with open(path) as f:
        lines = f.readlines()
    
    # Detect header
    start = 1 if lines[0].startswith("WeekEnding") else 0
    
    for i, line in enumerate(lines[start:], start=start+1):
        parts = line.strip().split("|")
        if len(parts) < 6:
            continue
        
        record_hash = hashlib.sha256(line.encode()).hexdigest()[:32]
        yield RawOTCRecord(
            week_ending=parts[0],
            tier=parts[1],
            symbol=parts[2].upper(),
            mpid=parts[3].upper(),
            total_shares=int(parts[4]),
            total_trades=int(parts[5]),
            source_line=i,
            record_hash=record_hash
        )
```

### `domains/otc/normalizer.py`

```python
"""Validate and normalize OTC records."""

from dataclasses import dataclass
from typing import Iterator
import re

from .connector import RawOTCRecord
from spine.core.rejects import Reject

SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
MPID_PATTERN = re.compile(r"^[A-Z0-9]{4}$")

@dataclass 
class ValidatedOTCRecord:
    """Record after validation (silver layer)."""
    week_ending: str
    tier: str
    symbol: str
    mpid: str
    total_shares: int
    total_trades: int
    record_hash: str

def normalize_records(
    records: Iterator[RawOTCRecord]
) -> tuple[list[ValidatedOTCRecord], list[Reject]]:
    """Validate records, return accepted and rejected."""
    accepted = []
    rejected = []
    
    for r in records:
        # Validate symbol
        if not SYMBOL_PATTERN.match(r.symbol):
            rejected.append(Reject(
                stage="NORMALIZE",
                reason_code="INVALID_SYMBOL",
                reason_detail=f"Symbol '{r.symbol}' invalid format",
                raw_data=r
            ))
            continue
        
        # Validate MPID
        if not MPID_PATTERN.match(r.mpid):
            rejected.append(Reject(
                stage="NORMALIZE",
                reason_code="INVALID_MPID",
                reason_detail=f"MPID '{r.mpid}' must be 4 alphanumeric",
                raw_data=r
            ))
            continue
        
        # Validate volume
        if r.total_shares < 0:
            rejected.append(Reject(
                stage="NORMALIZE",
                reason_code="NEGATIVE_VOLUME",
                reason_detail=f"Volume {r.total_shares} < 0",
                raw_data=r
            ))
            continue
        
        accepted.append(ValidatedOTCRecord(
            week_ending=r.week_ending,
            tier=r.tier,
            symbol=r.symbol,
            mpid=r.mpid,
            total_shares=r.total_shares,
            total_trades=r.total_trades,
            record_hash=r.record_hash
        ))
    
    return accepted, rejected
```

### `domains/otc/calculations.py`

```python
"""Pure calculation functions for OTC aggregations."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable
from dataclasses import dataclass

@dataclass
class SymbolSummary:
    symbol: str
    total_volume: int
    total_trades: int
    venue_count: int
    avg_trade_size: Decimal

@dataclass
class VenueShare:
    mpid: str
    volume: int
    trades: int
    market_share_pct: Decimal

@dataclass
class RollingMetrics:
    avg_volume: Decimal
    avg_trades: Decimal
    trend_direction: str  # UP | DOWN | FLAT
    trend_pct: Decimal
    weeks_in_window: int
    is_complete: bool

# Constants
TREND_THRESHOLD = Decimal("5.0")

def compute_symbol_summary(records: Iterable, symbol: str) -> SymbolSummary:
    """Aggregate venue records into symbol summary."""
    total_vol = 0
    total_trades = 0
    venues = set()
    
    for r in records:
        if r.symbol == symbol:
            total_vol += r.total_shares
            total_trades += r.total_trades
            venues.add(r.mpid)
    
    avg_size = Decimal(total_vol) / Decimal(total_trades) if total_trades > 0 else Decimal(0)
    
    return SymbolSummary(
        symbol=symbol,
        total_volume=total_vol,
        total_trades=total_trades,
        venue_count=len(venues),
        avg_trade_size=avg_size.quantize(Decimal("0.01"), ROUND_HALF_UP)
    )

def compute_venue_shares(records: Iterable) -> list[VenueShare]:
    """Compute market share per venue."""
    by_venue = {}
    total = 0
    
    for r in records:
        if r.mpid not in by_venue:
            by_venue[r.mpid] = {"volume": 0, "trades": 0}
        by_venue[r.mpid]["volume"] += r.total_shares
        by_venue[r.mpid]["trades"] += r.total_trades
        total += r.total_shares
    
    return [
        VenueShare(
            mpid=mpid,
            volume=data["volume"],
            trades=data["trades"],
            market_share_pct=(Decimal(data["volume"]) / Decimal(total) * 100).quantize(
                Decimal("0.01"), ROUND_HALF_UP
            ) if total > 0 else Decimal(0)
        )
        for mpid, data in by_venue.items()
    ]

def compute_trend(first_2w_avg: Decimal, last_2w_avg: Decimal) -> tuple[str, Decimal]:
    """Compute trend direction and percentage."""
    if first_2w_avg == 0:
        return "FLAT", Decimal(0)
    
    pct = ((last_2w_avg - first_2w_avg) / first_2w_avg * 100).quantize(
        Decimal("0.01"), ROUND_HALF_UP
    )
    
    if pct > TREND_THRESHOLD:
        return "UP", pct
    elif pct < -TREND_THRESHOLD:
        return "DOWN", pct
    return "FLAT", pct
```

### `domains/otc/pipelines.py` (Single File!)

```python
"""OTC pipelines - thin orchestration over core primitives."""

from pathlib import Path
from datetime import date

from spine.core.pipeline import Pipeline, PipelineResult, PipelineStatus
from spine.core.registry import register_pipeline
from spine.core.temporal import WeekEnding
from spine.core.execution import ExecutionContext, with_execution_context
from spine.core.manifest import WorkManifest
from spine.core.rejects import RejectSink
from spine.core.quality import QualityRunner, QualityCheck, QualityCategory
from spine.core.idempotency import IdempotencyChecker

from . import schema
from .connector import parse_finra_file
from .normalizer import normalize_records
from .calculations import compute_symbol_summary, compute_venue_shares, compute_trend


@register_pipeline("otc.ingest_week")
class IngestWeek(Pipeline):
    """Ingest FINRA file for one week."""
    
    def run(self, ctx: ExecutionContext) -> PipelineResult:
        week = WeekEnding(self.params["week_ending"])
        tier = schema.Tier(self.params["tier"])
        file_path = Path(self.params["file_path"])
        
        manifest = WorkManifest(self.conn, schema.TABLES["manifest"], ["week_ending", "tier"])
        rejects = RejectSink(self.conn, schema.TABLES["rejects"], ctx)
        idem = IdempotencyChecker(self.conn, schema.TABLES["manifest"], ["week_ending", "tier"])
        
        # Check if already done
        if not self.params.get("force") and idem.is_complete(
            {"week_ending": str(week), "tier": tier.value}, min_stage="INGESTED"
        ):
            return PipelineResult(status=PipelineStatus.COMPLETED, metrics={"skipped": True})
        
        # Parse file
        records = list(parse_finra_file(file_path))
        
        # Insert with dedup
        inserted = self._insert_raw(records, ctx)
        
        # Update manifest
        manifest.update_stage(
            {"week_ending": str(week), "tier": tier.value},
            stage="INGESTED",
            metrics={"row_count_inserted": inserted}
        )
        
        return PipelineResult(status=PipelineStatus.COMPLETED, metrics={"inserted": inserted})
    
    def _insert_raw(self, records, ctx) -> int:
        # Dedup and insert logic...
        pass


@register_pipeline("otc.normalize_week")
class NormalizeWeek(Pipeline):
    """Normalize raw records for one week."""
    
    def run(self, ctx: ExecutionContext) -> PipelineResult:
        week = WeekEnding(self.params["week_ending"])
        tier = schema.Tier(self.params["tier"])
        
        manifest = WorkManifest(self.conn, schema.TABLES["manifest"], ["week_ending", "tier"])
        rejects = RejectSink(self.conn, schema.TABLES["rejects"], ctx)
        
        # Fetch raw, normalize, write venue_volume, write rejects
        raw_records = self._fetch_raw(week, tier)
        accepted, rejected = normalize_records(raw_records)
        
        # Level 3: Delete existing, insert new
        self._write_venue_volume(week, tier, accepted, ctx)
        rejects.write_batch(rejected, {"week_ending": str(week), "tier": tier.value})
        
        manifest.update_stage(
            {"week_ending": str(week), "tier": tier.value},
            stage="NORMALIZED",
            metrics={"normalized": len(accepted), "rejected": len(rejected)}
        )
        
        return PipelineResult(status=PipelineStatus.COMPLETED, metrics={
            "normalized": len(accepted), "rejected": len(rejected)
        })


@register_pipeline("otc.aggregate_week")
class AggregateWeek(Pipeline):
    """Compute symbol summaries and venue shares for one week."""
    
    def run(self, ctx: ExecutionContext) -> PipelineResult:
        week = WeekEnding(self.params["week_ending"])
        tier = schema.Tier(self.params["tier"])
        
        manifest = WorkManifest(self.conn, schema.TABLES["manifest"], ["week_ending", "tier"])
        quality = QualityRunner(self.conn, schema.TABLES["quality"], ctx)
        
        # Fetch venue volumes, compute summaries
        records = self._fetch_venue_volume(week, tier)
        symbols = set(r.symbol for r in records)
        
        summaries = [compute_symbol_summary(records, s) for s in symbols]
        shares = compute_venue_shares(records)
        
        # Write results
        self._write_summaries(week, tier, summaries, ctx)
        self._write_shares(week, tier, shares, ctx)
        
        # Run quality checks
        quality.add_check(QualityCheck(
            name="market_share_sum",
            category=QualityCategory.BUSINESS_RULE,
            check_fn=lambda _: self._check_share_sum(shares)
        ))
        quality.run_all({"week": str(week), "tier": tier.value})
        
        manifest.update_stage(
            {"week_ending": str(week), "tier": tier.value},
            stage="AGGREGATED"
        )
        
        return PipelineResult(status=PipelineStatus.COMPLETED)


@register_pipeline("otc.compute_rolling_6w")
class ComputeRolling(Pipeline):
    """Compute 6-week rolling metrics."""
    
    def run(self, ctx: ExecutionContext) -> PipelineResult:
        # Use spine.core.rolling.RollingWindow
        from spine.core.rolling import RollingWindow
        
        week = WeekEnding(self.params.get("week_ending") or date.today())
        tier = schema.Tier(self.params["tier"])
        
        window = RollingWindow(window_size=6, bucket_type=WeekEnding)
        
        # For each symbol, compute rolling metrics
        symbols = self._get_symbols_in_window(week, tier)
        
        for symbol in symbols:
            result = window.compute(
                as_of=week,
                fetch_fn=lambda w: self._get_symbol_volume(w, tier, symbol),
                aggregate_fn=self._aggregate_rolling
            )
            self._write_rolling(week, tier, symbol, result, ctx)
        
        return PipelineResult(status=PipelineStatus.COMPLETED)


@register_pipeline("otc.backfill_range")
class BackfillRange(Pipeline):
    """Orchestrate multi-week backfill."""
    
    def run(self, ctx: ExecutionContext) -> PipelineResult:
        tier = schema.Tier(self.params["tier"])
        weeks = WeekEnding.last_n(self.params.get("weeks_back", 6))
        
        # Create batch context
        batch_ctx = with_execution_context(batch_id=f"backfill_{tier.value}_{ctx.execution_id[:8]}")
        
        for week in weeks:
            # Run each stage
            self._run_child("otc.ingest_week", {"week_ending": str(week), "tier": tier.value}, batch_ctx)
            self._run_child("otc.normalize_week", {"week_ending": str(week), "tier": tier.value}, batch_ctx)
            self._run_child("otc.aggregate_week", {"week_ending": str(week), "tier": tier.value}, batch_ctx)
        
        # Rolling and snapshot for latest
        self._run_child("otc.compute_rolling_6w", {"week_ending": str(weeks[-1]), "tier": tier.value}, batch_ctx)
        
        return PipelineResult(status=PipelineStatus.COMPLETED, metrics={"weeks": len(weeks)})
```

---

## 5. Cross-Tier Sharing Strategy

### Option B: Same Repo, Enforce Layering

```
market-spine/
├── packages/
│   ├── spine-core/                  # Platform primitives (pip installable)
│   │   ├── src/spine/core/
│   │   └── pyproject.toml
│   └── spine-domains-otc/           # OTC domain (pip installable)
│       ├── src/spine/domains/otc/
│       └── pyproject.toml
│
├── market-spine-basic/              # Basic tier app
│   ├── pyproject.toml               # Depends on spine-core, spine-domains-otc
│   └── src/market_spine_basic/
│       ├── db.py                    # SQLite connection
│       ├── runner.py                # Sync runner
│       └── cli.py
│
├── market-spine-intermediate/       # Intermediate tier app
│   ├── pyproject.toml               # Same dependencies + httpx, fastapi
│   └── src/market_spine_intermediate/
│       ├── db.py                    # PostgreSQL connection
│       ├── worker.py                # Background worker
│       ├── api/                     # REST endpoints
│       └── cli.py
│
└── market-spine-advanced/           # Advanced tier app
    ├── pyproject.toml               # Same dependencies + celery, redis, boto3
    └── src/market_spine_advanced/
        ├── db.py                    # PostgreSQL
        ├── storage.py               # S3 adapter
        ├── tasks.py                 # Celery tasks
        └── scheduler.py
```

### What Changes Per Tier

| Component | Basic | Intermediate | Advanced |
|-----------|-------|--------------|----------|
| `spine.core.*` | Same | Same | Same |
| `spine.domains.otc.*` | Same | Same | Same |
| Connection | `sqlite3` | `asyncpg` | `asyncpg` |
| Runner | Sync loop | `asyncio` | Celery worker |
| Pipeline.run() | Blocking | `async def` | Celery task |
| Storage | Local files | PostgreSQL | S3 + PostgreSQL |

### Tier Adapter Pattern

```python
# market-spine-basic/src/runner.py
from spine.core.pipeline import Pipeline

def run_pipeline(name: str, params: dict):
    """Basic: synchronous execution."""
    pipeline_cls = get_pipeline(name)
    pipeline = pipeline_cls(params)
    pipeline.conn = get_sqlite_connection()
    return pipeline.run(with_execution_context())

# market-spine-intermediate/src/worker.py  
async def run_pipeline_async(name: str, params: dict):
    """Intermediate: async execution."""
    pipeline_cls = get_pipeline(name)
    pipeline = pipeline_cls(params)
    pipeline.conn = await get_postgres_connection()
    return await pipeline.run_async(with_execution_context())

# market-spine-advanced/src/tasks.py
@celery.task
def run_pipeline_celery(name: str, params: dict):
    """Advanced: Celery task."""
    pipeline_cls = get_pipeline(name)
    pipeline = pipeline_cls(params)
    pipeline.conn = get_postgres_connection()
    return pipeline.run(with_execution_context())
```

---

## 6. Migration Steps (Stop Points)

Each step is a commit where tests pass.

### Step 1: Create `spine.core.temporal` ✓
- Move `WeekEnding` from `otc/validators.py` to `spine/core/temporal.py`
- Add `WeekRange`, `last_n` helper
- Update imports in OTC
- **Tests pass**: WeekEnding validation works

### Step 2: Create `spine.core.execution` ✓
- Create `ExecutionContext` dataclass
- Add to pipeline base class
- Update OTC pipelines to accept context
- **Tests pass**: Pipelines run with context

### Step 3: Create `spine.core.manifest` ✓
- Create generic `WorkManifest` class
- OTC uses it with `otc_week_manifest` table
- **Tests pass**: Manifest updates work

### Step 4: Create `spine.core.rejects` ✓
- Create `RejectSink` class
- OTC uses it for reject writes
- **Tests pass**: Rejects recorded

### Step 5: Create `spine.core.quality` ✓
- Create `QualityRunner`, `QualityCheck`
- OTC uses for quality checks
- **Tests pass**: Quality checks recorded

### Step 6: Create `spine.core.idempotency` ✓
- Create `IdempotencyChecker`
- OTC uses for skip/force logic
- **Tests pass**: Idempotency works

### Step 7: Create `spine.core.rolling` ✓
- Create `RollingWindow` generic class
- OTC uses for 6-week rolling
- **Tests pass**: Rolling computed

### Step 8: Consolidate OTC pipelines ✓
- Merge 6 pipeline files into one `pipelines.py`
- Each pipeline ~30-50 lines
- **Tests pass**: Full workflow works

### Step 9: Consolidate OTC docs ✓
- Replace 12 docs with:
  - `docs/domains/otc/README.md` (overview + usage)
  - Code comments in source files
- **Tests pass**: No code changes

### Step 10: Verify cross-tier ✓
- Import `spine.domains.otc` into Intermediate
- Verify calculations work unchanged
- **Tests pass**: Same results

---

## 7. Success Metrics

After refactor:

| Metric | Before | After |
|--------|--------|-------|
| OTC domain files | 12+ | 5 |
| OTC domain lines | ~2000 | ~500 |
| `spine.core` modules | 3 | 10 |
| New domain effort | Copy 10 patterns | Compose primitives |
| Cross-tier portability | Rewrite | Import |

### Adding New Calculation (e.g., `liquidity_score_v1`)

**Files to change:**

1. `domains/otc/calculations.py` - Add pure function `compute_liquidity_score()`
2. `domains/otc/pipelines.py` - Call it from `AggregateWeek.run()`

**That's it.** No new manifest logic, no new reject handling, no new quality framework.

---

## 8. Appendix: Docs Consolidation

Replace 12 separate docs with:

```
docs/
├── architecture/
│   ├── CORE_PRIMITIVES.md          # What's in spine.core
│   └── DOMAIN_TEMPLATE.md          # How to add a domain
├── domains/
│   └── otc/
│       └── README.md               # OTC-specific: connector format, calculations
└── tutorials/
    └── ADD_WEEKLY_CALC.md          # Step-by-step: add a new weekly calc
```

Each source file gets header docstring explaining purpose. Code is the documentation.
