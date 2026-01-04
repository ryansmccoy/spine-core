# Patch Plan: Platform Primitives Extraction

> **Objective**: Migrate from heavy OTC domain to thin domain + thick platform in 10 incremental steps.
> **Each step is a green commit** — tests pass at every stop point.

---

## Prerequisites

Before starting:
```powershell
# Ensure tests pass at baseline
pytest tests/domains/otc/ -v
```

---

## Step 1: Create `spine.core.temporal`

**Goal**: Extract `WeekEnding` to core, make it generic.

### 1.1 Create core directory structure

```powershell
mkdir -p market-spine-basic/src/spine/core
```

### 1.2 Create `spine/core/__init__.py`

```python
"""Spine Core - Platform primitives for temporal data processing."""
```

### 1.3 Create `spine/core/temporal.py`

```python
"""Temporal primitives for weekly/monthly workflows."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterator, Union


@dataclass(frozen=True, slots=True)
class WeekEnding:
    """
    Validated Friday date for weekly workflows.
    
    FINRA publishes OTC data every Friday. This value object ensures
    all week_ending values are valid Fridays.
    
    Examples:
        >>> WeekEnding("2025-12-26")  # OK - Friday
        >>> WeekEnding("2025-12-25")  # Raises ValueError - Thursday
        >>> WeekEnding.from_any_date(date(2025, 12, 23))  # Returns 2025-12-26
    """
    value: date
    
    def __init__(self, value: Union[str, date]):
        if isinstance(value, str):
            parsed = date.fromisoformat(value)
        elif isinstance(value, date):
            parsed = value
        else:
            raise TypeError(f"Expected str or date, got {type(value).__name__}")
        
        if parsed.weekday() != 4:  # Friday = 4
            day_name = parsed.strftime("%A")
            nearest = _nearest_friday(parsed)
            raise ValueError(
                f"week_ending must be Friday, got {parsed} ({day_name}). "
                f"Nearest Friday: {nearest}"
            )
        
        object.__setattr__(self, "value", parsed)
    
    @classmethod
    def from_any_date(cls, d: date) -> "WeekEnding":
        """Create WeekEnding from any date, finding containing week's Friday."""
        return cls(_nearest_friday(d))
    
    @classmethod
    def last_n(cls, n: int, as_of: date = None) -> list["WeekEnding"]:
        """
        Get last N week endings including as_of date's week.
        
        Args:
            n: Number of weeks (1 = just this week)
            as_of: Reference date (default: today)
            
        Returns:
            List of WeekEnding, oldest first
        """
        ref = as_of or date.today()
        latest = cls.from_any_date(ref)
        weeks = [cls(latest.value - timedelta(weeks=i)) for i in range(n)]
        return list(reversed(weeks))  # Oldest first
    
    @classmethod
    def range(cls, start: "WeekEnding", end: "WeekEnding") -> Iterator["WeekEnding"]:
        """Generate all Fridays from start to end (inclusive)."""
        current = start.value
        while current <= end.value:
            yield cls(current)
            current += timedelta(weeks=1)
    
    def previous(self, n: int = 1) -> "WeekEnding":
        """Get N weeks before this one."""
        return WeekEnding(self.value - timedelta(weeks=n))
    
    def __str__(self) -> str:
        return self.value.isoformat()
    
    def __repr__(self) -> str:
        return f"WeekEnding({self.value.isoformat()!r})"
    
    def __lt__(self, other: "WeekEnding") -> bool:
        return self.value < other.value
    
    def __le__(self, other: "WeekEnding") -> bool:
        return self.value <= other.value


def _nearest_friday(d: date) -> date:
    """Find the Friday of the week containing date d."""
    days_ahead = 4 - d.weekday()  # Friday = 4
    if days_ahead < 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)
```

### 1.4 Update OTC to import from core

```python
# domains/otc/validators.py - Remove WeekEnding class, add:
from spine.core.temporal import WeekEnding

# Re-export for backwards compatibility
__all__ = ["WeekEnding", "Symbol", "MPID"]
```

### 1.5 Run tests

```powershell
pytest tests/domains/otc/ -v -k "week"
# Should pass - WeekEnding works the same
```

**STOP POINT 1 ✓**

---

## Step 2: Create `spine.core.execution`

**Goal**: Standardize execution context for lineage tracking.

### 2.1 Create `spine/core/execution.py`

```python
"""Execution context for pipeline lineage tracking."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class ExecutionContext:
    """
    Context passed through pipeline execution for lineage.
    
    Every pipeline execution gets an execution_id. When pipelines
    call sub-pipelines, the parent_execution_id links them.
    Batch operations share a batch_id.
    """
    
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
    
    def with_batch(self, batch_id: str) -> "ExecutionContext":
        """Create copy with batch_id set."""
        return ExecutionContext(
            execution_id=self.execution_id,
            batch_id=batch_id,
            parent_execution_id=self.parent_execution_id,
            started_at=self.started_at
        )


def new_context(batch_id: str = None) -> ExecutionContext:
    """Create new root execution context."""
    return ExecutionContext(batch_id=batch_id)


def new_batch_id(prefix: str = "") -> str:
    """Generate a new batch ID."""
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    short_id = str(uuid.uuid4())[:8]
    return f"{prefix}_{ts}_{short_id}" if prefix else f"batch_{ts}_{short_id}"
```

### 2.2 Update Pipeline base class

```python
# pipelines/base.py - Add context parameter
class Pipeline(ABC):
    def __init__(self, params: dict = None, ctx: ExecutionContext = None):
        self.params = params or {}
        self.ctx = ctx or new_context()
```

### 2.3 Update OTC pipelines to use context

```python
# domains/otc/pipelines.py
from spine.core.execution import ExecutionContext, new_context

class OTCIngestPipeline(Pipeline):
    def run(self) -> PipelineResult:
        # Use self.ctx.execution_id for lineage
        conn.execute("INSERT INTO otc_raw (..., execution_id) VALUES (..., ?)",
                     (..., self.ctx.execution_id))
```

### 2.4 Run tests

```powershell
pytest tests/domains/otc/ -v
# Should pass - context is optional, defaults work
```

**STOP POINT 2 ✓**

---

## Step 3: Create `spine.core.manifest`

**Goal**: Generic work manifest for multi-stage workflows.

### 3.1 Create `spine/core/manifest.py`

```python
"""Generic work manifest for tracking multi-stage workflows."""

from typing import Optional, Any
from datetime import datetime


class WorkManifest:
    """
    Track processing stages for work items.
    
    Each work item is identified by a compound key (e.g., week_ending + tier).
    Stages progress in order. Manifest records metrics at each stage.
    
    Example:
        manifest = WorkManifest(conn, "otc_week_manifest", ["week_ending", "tier"])
        manifest.ensure_exists({"week_ending": "2025-12-26", "tier": "NMS_TIER_1"})
        manifest.advance_to(key, "INGESTED", metrics={"rows": 1000})
    """
    
    def __init__(
        self,
        conn,
        table: str,
        key_columns: list[str],
        stage_column: str = "stage",
        initial_stage: str = "PENDING"
    ):
        self.conn = conn
        self.table = table
        self.key_columns = key_columns
        self.stage_column = stage_column
        self.initial_stage = initial_stage
    
    def get_stage(self, key: dict[str, Any]) -> Optional[str]:
        """Get current stage for work item, or None if not exists."""
        where = " AND ".join(f"{k} = ?" for k in self.key_columns)
        values = tuple(key[k] for k in self.key_columns)
        
        row = self.conn.execute(
            f"SELECT {self.stage_column} FROM {self.table} WHERE {where}",
            values
        ).fetchone()
        
        return row[0] if row else None
    
    def ensure_exists(self, key: dict[str, Any], **initial_values) -> bool:
        """Create manifest entry if not exists. Returns True if created."""
        if self.get_stage(key) is not None:
            return False
        
        columns = list(self.key_columns) + [self.stage_column] + list(initial_values.keys())
        values = [key[k] for k in self.key_columns] + [self.initial_stage] + list(initial_values.values())
        placeholders = ", ".join("?" * len(columns))
        
        self.conn.execute(
            f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(values)
        )
        return True
    
    def advance_to(self, key: dict[str, Any], stage: str, **metrics) -> None:
        """Update stage and optional metrics. Creates if not exists."""
        self.ensure_exists(key)
        
        sets = [f"{self.stage_column} = ?", "updated_at = ?"]
        values = [stage, datetime.utcnow().isoformat()]
        
        for col, val in metrics.items():
            sets.append(f"{col} = ?")
            values.append(val)
        
        where = " AND ".join(f"{k} = ?" for k in self.key_columns)
        values.extend(key[k] for k in self.key_columns)
        
        self.conn.execute(
            f"UPDATE {self.table} SET {', '.join(sets)} WHERE {where}",
            tuple(values)
        )
    
    def is_at_least(self, key: dict[str, Any], min_stage: str, stages: list[str]) -> bool:
        """Check if work item is at or past min_stage."""
        current = self.get_stage(key)
        if current is None:
            return False
        
        try:
            current_idx = stages.index(current)
            min_idx = stages.index(min_stage)
            return current_idx >= min_idx
        except ValueError:
            return False
```

### 3.2 Update OTC to use WorkManifest

```python
# domains/otc/pipelines.py
from spine.core.manifest import WorkManifest
from .schema import TABLES, STAGES

class OTCIngestPipeline(Pipeline):
    def run(self):
        manifest = WorkManifest(conn, TABLES["manifest"], ["week_ending", "tier"])
        
        # Check if already done
        if manifest.is_at_least(key, "INGESTED", STAGES):
            return skip_result()
        
        # ... do work ...
        
        manifest.advance_to(key, "INGESTED", row_count_inserted=inserted)
```

### 3.3 Run tests

```powershell
pytest tests/domains/otc/ -v -k "manifest"
```

**STOP POINT 3 ✓**

---

## Step 4: Create `spine.core.rejects`

**Goal**: Standardized reject handling for any domain.

### 4.1 Create `spine/core/rejects.py`

```python
"""Standardized reject handling."""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Optional


@dataclass
class Reject:
    """A rejected record with reason."""
    stage: str              # INGEST | NORMALIZE | AGGREGATE
    reason_code: str        # Machine-readable: INVALID_SYMBOL
    reason_detail: str      # Human-readable explanation
    raw_data: Any = None    # Original record (serializable)
    source_locator: str = None
    line_number: int = None


class RejectSink:
    """
    Write rejects to storage with lineage.
    
    Example:
        sink = RejectSink(conn, "otc_rejects", ctx)
        sink.write(Reject(stage="NORMALIZE", reason_code="INVALID_SYMBOL", ...))
    """
    
    def __init__(self, conn, table: str, execution_id: str, batch_id: str = None):
        self.conn = conn
        self.table = table
        self.execution_id = execution_id
        self.batch_id = batch_id
    
    def write(self, reject: Reject, domain_key: dict = None) -> None:
        """Write single reject."""
        self._insert([reject], domain_key)
    
    def write_batch(self, rejects: list[Reject], domain_key: dict = None) -> int:
        """Write multiple rejects. Returns count written."""
        if not rejects:
            return 0
        self._insert(rejects, domain_key)
        return len(rejects)
    
    def _insert(self, rejects: list[Reject], domain_key: dict) -> None:
        key_cols = list(domain_key.keys()) if domain_key else []
        
        columns = [
            "stage", "reason_code", "reason_detail", "raw_line",
            "source_locator", "line_number", "execution_id", "batch_id", "created_at"
        ] + key_cols
        
        for reject in rejects:
            raw_str = str(reject.raw_data) if reject.raw_data else None
            values = [
                reject.stage,
                reject.reason_code,
                reject.reason_detail,
                raw_str,
                reject.source_locator,
                reject.line_number,
                self.execution_id,
                self.batch_id,
                datetime.utcnow().isoformat()
            ] + [domain_key.get(k) for k in key_cols]
            
            placeholders = ", ".join("?" * len(columns))
            self.conn.execute(
                f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values)
            )
```

### 4.2 Update OTC normalize to use RejectSink

```python
# domains/otc/pipelines.py
from spine.core.rejects import RejectSink, Reject

def run(self):
    sink = RejectSink(conn, TABLES["rejects"], self.ctx.execution_id, self.ctx.batch_id)
    
    for record in records:
        if not valid(record):
            sink.write(Reject(
                stage="NORMALIZE",
                reason_code="INVALID_SYMBOL",
                reason_detail=f"Bad symbol: {record.symbol}",
                raw_data=record
            ), domain_key={"week_ending": week, "tier": tier})
```

### 4.3 Run tests

```powershell
pytest tests/domains/otc/ -v -k "reject"
```

**STOP POINT 4 ✓**

---

## Step 5: Create `spine.core.quality`

**Goal**: Quality check framework for any domain.

### 5.1 Create `spine/core/quality.py`

```python
"""Quality check framework."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Any, Optional


class QualityStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class QualityCategory(str, Enum):
    INTEGRITY = "INTEGRITY"
    COMPLETENESS = "COMPLETENESS"
    BUSINESS_RULE = "BUSINESS_RULE"


@dataclass
class QualityResult:
    """Result of one quality check."""
    status: QualityStatus
    message: str
    actual_value: Any = None
    expected_value: Any = None


@dataclass
class QualityCheck:
    """Definition of a quality check."""
    name: str
    category: QualityCategory
    check_fn: Callable[[dict], QualityResult]


class QualityRunner:
    """
    Run quality checks and record results.
    
    Example:
        runner = QualityRunner(conn, "otc_quality_checks", execution_id)
        runner.add_check(QualityCheck("share_sum", BUSINESS_RULE, check_share_sum))
        results = runner.run_all(context={"week": "2025-12-26"})
    """
    
    def __init__(self, conn, table: str, execution_id: str, batch_id: str = None):
        self.conn = conn
        self.table = table
        self.execution_id = execution_id
        self.batch_id = batch_id
        self.checks: list[QualityCheck] = []
    
    def add_check(self, check: QualityCheck) -> "QualityRunner":
        """Add a check. Returns self for chaining."""
        self.checks.append(check)
        return self
    
    def run_all(self, context: dict) -> dict[str, QualityStatus]:
        """Run all checks, record results, return status summary."""
        results = {}
        
        for check in self.checks:
            result = check.check_fn(context)
            results[check.name] = result.status
            self._record(check, result, context)
        
        return results
    
    def _record(self, check: QualityCheck, result: QualityResult, context: dict) -> None:
        self.conn.execute(
            f"""INSERT INTO {self.table} 
                (check_name, category, status, message, actual_value, expected_value,
                 execution_id, batch_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                check.name,
                check.category.value,
                result.status.value,
                result.message,
                str(result.actual_value) if result.actual_value else None,
                str(result.expected_value) if result.expected_value else None,
                self.execution_id,
                self.batch_id,
                datetime.utcnow().isoformat()
            )
        )
```

### 5.2 Update OTC aggregate to use QualityRunner

```python
# domains/otc/pipelines.py
from spine.core.quality import QualityRunner, QualityCheck, QualityCategory, QualityResult, QualityStatus

def check_market_share_sum(ctx: dict) -> QualityResult:
    total = sum(s.market_share_pct for s in ctx["shares"])
    if 99.9 <= total <= 100.1:
        return QualityResult(QualityStatus.PASS, "Sum within tolerance", actual_value=total)
    return QualityResult(QualityStatus.FAIL, f"Sum {total} outside 99.9-100.1", actual_value=total)

class AggregateWeek(Pipeline):
    def run(self):
        runner = QualityRunner(conn, TABLES["quality"], self.ctx.execution_id)
        runner.add_check(QualityCheck("market_share_sum", QualityCategory.BUSINESS_RULE, check_market_share_sum))
        runner.run_all({"shares": venue_shares})
```

### 5.3 Run tests

```powershell
pytest tests/domains/otc/ -v -k "quality"
```

**STOP POINT 5 ✓**

---

## Step 6: Create `spine.core.idempotency`

**Goal**: Idempotency helpers for skip/force/delete-insert patterns.

### 6.1 Create `spine/core/idempotency.py`

```python
"""Idempotency helpers for pipeline execution."""

from enum import IntEnum
from typing import Any


class IdempotencyLevel(IntEnum):
    """Pipeline idempotency classification."""
    L1_APPEND = 1       # Always inserts, external dedup
    L2_INPUT = 2        # Same input → same output (hash dedup)
    L3_STATE = 3        # Re-run → same final state (delete+insert)


class IdempotencyHelper:
    """
    Helper for idempotent pipeline patterns.
    
    Example:
        helper = IdempotencyHelper(conn)
        
        # Check if should skip
        if helper.is_complete("otc_week_manifest", key, "INGESTED", STAGES):
            return skip_result()
        
        # Level 3: Delete before insert
        helper.delete_for_key("otc_venue_volume", key)
        # ... insert new data ...
    """
    
    def __init__(self, conn):
        self.conn = conn
    
    def is_complete(
        self,
        manifest_table: str,
        key: dict[str, Any],
        min_stage: str,
        stages: list[str],
        stage_column: str = "stage"
    ) -> bool:
        """Check if work item already at or past min_stage."""
        where = " AND ".join(f"{k} = ?" for k in key.keys())
        values = tuple(key.values())
        
        row = self.conn.execute(
            f"SELECT {stage_column} FROM {manifest_table} WHERE {where}",
            values
        ).fetchone()
        
        if not row:
            return False
        
        current = row[0]
        try:
            return stages.index(current) >= stages.index(min_stage)
        except ValueError:
            return False
    
    def delete_for_key(self, table: str, key: dict[str, Any]) -> int:
        """Delete all rows matching key. Returns count deleted."""
        where = " AND ".join(f"{k} = ?" for k in key.keys())
        values = tuple(key.values())
        
        cursor = self.conn.execute(f"DELETE FROM {table} WHERE {where}", values)
        return cursor.rowcount
    
    def hash_exists(self, table: str, hash_column: str, hash_value: str) -> bool:
        """Check if record hash already exists (Level 2 dedup)."""
        row = self.conn.execute(
            f"SELECT 1 FROM {table} WHERE {hash_column} = ? LIMIT 1",
            (hash_value,)
        ).fetchone()
        return row is not None
```

### 6.2 Update OTC pipelines to use IdempotencyHelper

### 6.3 Run tests

```powershell
pytest tests/domains/otc/ -v
```

**STOP POINT 6 ✓**

---

## Step 7: Create `spine.core.rolling`

**Goal**: Generic rolling window helper for time-series.

### 7.1 Create `spine/core/rolling.py`

```python
"""Rolling window utilities for time-series calculations."""

from dataclasses import dataclass
from typing import TypeVar, Generic, Callable, Any, Optional
from datetime import date, timedelta

T = TypeVar("T")  # Time bucket type
V = TypeVar("V")  # Value type


@dataclass
class RollingResult:
    """Result of a rolling window computation."""
    aggregates: dict[str, Any]    # Domain-specific aggregates
    periods_present: int          # How many periods had data
    periods_total: int            # Window size
    is_complete: bool             # All periods present


class RollingWindow(Generic[T]):
    """
    Generic rolling window over time buckets.
    
    Example:
        window = RollingWindow(size=6, step_back=lambda w: w.previous())
        
        result = window.compute(
            as_of=week,
            fetch_fn=lambda w: get_volume(w, symbol),
            aggregate_fn=compute_averages
        )
    """
    
    def __init__(self, size: int, step_back: Callable[[T], T]):
        """
        Args:
            size: Number of periods in window
            step_back: Function to get previous period (e.g., week.previous())
        """
        self.size = size
        self.step_back = step_back
    
    def get_window(self, as_of: T) -> list[T]:
        """Get all periods in the window, oldest first."""
        periods = []
        current = as_of
        for _ in range(self.size):
            periods.append(current)
            current = self.step_back(current)
        return list(reversed(periods))
    
    def compute(
        self,
        as_of: T,
        fetch_fn: Callable[[T], Optional[V]],
        aggregate_fn: Callable[[list[tuple[T, V]]], dict[str, Any]]
    ) -> RollingResult:
        """
        Compute rolling aggregate.
        
        Args:
            as_of: Current period (end of window)
            fetch_fn: Get value for period (None if missing)
            aggregate_fn: Combine (period, value) pairs into result dict
        """
        periods = self.get_window(as_of)
        values = [(p, fetch_fn(p)) for p in periods]
        present = [(p, v) for p, v in values if v is not None]
        
        aggregates = aggregate_fn(present) if present else {}
        
        return RollingResult(
            aggregates=aggregates,
            periods_present=len(present),
            periods_total=self.size,
            is_complete=len(present) == self.size
        )
```

### 7.2 Update OTC rolling pipeline

```python
from spine.core.rolling import RollingWindow, RollingResult
from spine.core.temporal import WeekEnding

def compute_rolling(week, tier, symbol, conn):
    window = RollingWindow(size=6, step_back=lambda w: w.previous())
    
    def fetch_volume(w: WeekEnding) -> Optional[int]:
        row = conn.execute(
            "SELECT total_volume FROM otc_symbol_summary WHERE week_ending=? AND symbol=?",
            (str(w), symbol)
        ).fetchone()
        return row[0] if row else None
    
    def aggregate(data: list[tuple[WeekEnding, int]]) -> dict:
        volumes = [v for _, v in data]
        return {
            "avg_volume": sum(volumes) / len(volumes),
            "min_volume": min(volumes),
            "max_volume": max(volumes),
        }
    
    return window.compute(week, fetch_volume, aggregate)
```

### 7.3 Run tests

```powershell
pytest tests/domains/otc/ -v -k "rolling"
```

**STOP POINT 7 ✓**

---

## Step 8: Consolidate OTC Pipelines

**Goal**: Merge 6 pipeline files into one thin `pipelines.py`.

### 8.1 Create `domains/otc/schema.py`

```python
"""OTC domain constants."""

from enum import Enum

class Tier(str, Enum):
    NMS_TIER_1 = "NMS_TIER_1"
    NMS_TIER_2 = "NMS_TIER_2"
    OTC = "OTC"

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

STAGES = ["PENDING", "INGESTED", "NORMALIZED", "AGGREGATED", "ROLLING", "SNAPSHOT"]
```

### 8.2 Rewrite `domains/otc/pipelines.py` (single file)

All 6 pipelines in one file, each ~40-60 lines, using core primitives.

### 8.3 Delete old pipeline files

```powershell
rm domains/otc/pipelines/*.py  # If using package structure
```

### 8.4 Run full test suite

```powershell
pytest tests/domains/otc/ -v
```

**STOP POINT 8 ✓**

---

## Step 9: Consolidate Documentation

**Goal**: Replace 12 docs with 2-3 focused docs.

### 9.1 Create `docs/domains/otc/README.md`

Single page: overview, file format, calculations, usage examples.

### 9.2 Archive old docs

```powershell
mv docs/implementation/otc-multiweek docs/archive/otc-multiweek-detailed
```

### 9.3 Add source docstrings

Each source file gets comprehensive docstring.

**STOP POINT 9 ✓**

---

## Step 10: Verify Cross-Tier Portability

**Goal**: Prove same domain code works in Intermediate.

### 10.1 Add spine.core to Intermediate

```python
# market-spine-intermediate/pyproject.toml
[project.dependencies]
spine-core = {path = "../packages/spine-core"}
spine-domains-otc = {path = "../packages/spine-domains-otc"}
```

### 10.2 Create Intermediate runner

```python
# market-spine-intermediate/src/runner.py
from spine.domains.otc import pipelines  # Same code!
from spine.core.execution import new_context

async def run_pipeline(name: str, params: dict):
    # Only difference: async DB connection
    conn = await get_postgres_connection()
    ctx = new_context()
    
    pipeline_cls = get_pipeline(name)
    pipeline = pipeline_cls(params, ctx)
    pipeline.conn = conn
    
    return pipeline.run()  # Same domain logic!
```

### 10.3 Run Intermediate tests

```powershell
cd market-spine-intermediate
pytest tests/domains/otc/ -v
# Same tests, different backend
```

**STOP POINT 10 ✓** — **REFACTOR COMPLETE**

---

## Summary: Files Changed

### New Files (spine.core)

| File | Lines | Purpose |
|------|-------|---------|
| `spine/core/__init__.py` | 5 | Package init |
| `spine/core/temporal.py` | 80 | WeekEnding, ranges |
| `spine/core/execution.py` | 50 | ExecutionContext |
| `spine/core/manifest.py` | 80 | WorkManifest |
| `spine/core/rejects.py` | 60 | RejectSink |
| `spine/core/quality.py` | 80 | QualityRunner |
| `spine/core/idempotency.py` | 60 | IdempotencyHelper |
| `spine/core/rolling.py` | 60 | RollingWindow |
| **Total** | **~475** | |

### OTC Domain (After)

| File | Lines | Purpose |
|------|-------|---------|
| `domains/otc/__init__.py` | 5 | Package init |
| `domains/otc/schema.py` | 25 | Tables, stages, tiers |
| `domains/otc/connector.py` | 50 | Parse FINRA PSV |
| `domains/otc/normalizer.py` | 60 | Validate records |
| `domains/otc/calculations.py` | 80 | Pure aggregation functions |
| `domains/otc/pipelines.py` | 200 | All 6 pipelines |
| **Total** | **~420** | |

### Deleted/Archived

- `docs/implementation/otc-multiweek/*.md` (12 files) → archived
- `domains/otc/validators.py` → moved to core
- `domains/otc/pipelines/*.py` (6 files) → consolidated

---

## Verification Checklist

After completing all steps:

- [ ] `pytest tests/` passes in market-spine-basic
- [ ] `pytest tests/` passes in market-spine-intermediate (if set up)
- [ ] OTC domain is 5-6 files, <500 lines total
- [ ] `spine.core` has 8 modules, ~500 lines total
- [ ] Adding new calc requires changes to 1-2 files only
- [ ] No `import sqlite3` or `import asyncpg` in domain code
