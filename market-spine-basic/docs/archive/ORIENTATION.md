# Market-Spine Basic: Repository Orientation

**Last Updated**: January 2, 2026  
**Audience**: Developers working on the Basic tier or adding new domains

---

## Table of Contents

1. [You Are Here: App vs Library vs Domains](#you-are-here-app-vs-library-vs-domains)
2. [Annotated Tree](#annotated-tree)
3. [Canonical Entrypoints](#canonical-entrypoints)
4. [Running OTC End-to-End](#running-otc-end-to-end)
5. [Where to Change Things](#where-to-change-things)

---

## You Are Here: App vs Library vs Domains

The `market-spine-basic` repository has **two distinct code trees**:

### 1. Application Layer: `src/market_spine/`

**Purpose**: Basic tier infrastructure for running pipelines.

**NOT shareable** across tiers. Intermediate/Advanced/Full have their own app layers.

**Components**:
- **CLI** (`cli.py`) - Click-based command-line interface (`spine` command)
- **Dispatcher** (`dispatcher.py`) - Routes pipeline execution requests
- **Registry** (`registry.py`) - Discovers and registers pipelines via `@register_pipeline`
- **Runner** (`runner.py`) - Executes pipeline `.run()` methods
- **DB** (`db.py`) - SQLite connection factory
- **Base classes** (`pipelines/base.py`) - `Pipeline`, `PipelineResult`, `PipelineStatus`

**Storage**: SQLite (`spine.db`)

### 2. Shared Library Layer: `src/spine/`

**Purpose**: Cross-tier reusable code.

**Shareable** across all tiers. Same code runs unchanged in Basic/Intermediate/Advanced/Full.

**Structure**:
```
spine/
├── core/            # Platform primitives (domain-agnostic)
│   ├── temporal     # WeekEnding, date ranges
│   ├── execution    # ExecutionContext, lineage tracking
│   ├── hashing      # Record deduplication
│   ├── manifest     # Multi-stage workflow tracking (Option A: upsert-based)
│   ├── idempotency  # Skip/force, delete+insert helpers
│   ├── rejects      # Validation failure recording
│   ├── quality      # Quality check framework
│   ├── rolling      # Rolling window calculations
│   ├── storage      # DB-agnostic sync protocols
│   └── schema       # Core infrastructure tables
│
└── domains/         # Domain-specific code
    └── otc/         # OTC weekly transparency domain
        ├── schema       # DOMAIN constant, tier enum, table names, stages
        ├── connector    # Parse FINRA PSV files
        ├── normalizer   # Validation logic
        ├── calculations # Business logic (pure functions)
        └── pipelines    # Pipeline orchestration (@register_pipeline)
```

**Design Principles**:
- **Sync-only**: All primitives are synchronous (no async/await)
- **Thin domains, thick platform**: Domains compose core primitives, contain minimal logic
- **Pure business logic**: Calculations are pure functions (no I/O, no side effects)

### 3. Domain Code: Where Does It Live?

**CANONICAL LOCATION**: `src/spine/domains/{domain_name}/`

**Why here**:
- Shareable across tiers
- Built on `spine.core` primitives (not tier-specific infrastructure)
- Can be packaged separately (`packages/spine-domains-otc/`)

**NOT in `src/market_spine/domains/`** - That's legacy/deprecated structure.

---

## Annotated Tree

**Legend**: 🎯 Critical entrypoint | 🟢 Shareable library | 🔴 Tier-specific app | ⚠️ Legacy/duplicate

```
market-spine-basic/
│
├── pyproject.toml              # 🎯 Package config, defines "spine" CLI command
├── README.md                   # High-level documentation
├── spine.db                    # SQLite database (local storage)
├── query_otc.py                # Quick query script for testing
│
├── data/                       # Sample FINRA input files
│   └── finra/
│       └── nms_tier1_2026-01-02.csv
│
├── migrations/                 # SQL migration files
│   ├── 001_core_executions.sql    # Legacy execution tracking (not used)
│   └── 020_otc_tables.sql         # OTC domain tables (otc_raw, otc_venue_volume, etc.)
│
├── src/
│   ├── market_spine/           # 🔴 APPLICATION LAYER (Basic tier only)
│   │   ├── cli.py              # 🎯 CLI ENTRYPOINT - defines "spine" command
│   │   ├── dispatcher.py       # 🎯 PIPELINE DISPATCHER - routes execution
│   │   ├── registry.py         # 🎯 PIPELINE REGISTRY - discovers @register_pipeline
│   │   ├── runner.py           # Pipeline execution engine
│   │   ├── db.py               # 🎯 DB CONNECTION FACTORY - get_connection()
│   │   ├── config.py           # App-level configuration
│   │   │
│   │   ├── pipelines/
│   │   │   └── base.py         # Pipeline, PipelineResult, PipelineStatus base classes
│   │   │
│   │   ├── domains/            # ⚠️ LEGACY - DO NOT USE
│   │   │   ├── example/        # ⚠️ Old example domain (unused)
│   │   │   └── otc/            # ⚠️ DUPLICATE OTC (outdated, use spine/domains/otc instead)
│   │   │
│   │   └── services/           # (empty - legacy structure)
│   │
│   └── spine/                  # 🟢 SHARED LIBRARY LAYER (cross-tier)
│       ├── core/               # 🎯 CORE PRIMITIVES (platform)
│       │   ├── __init__.py     # Exports all primitives
│       │   ├── schema.py       # 🎯 Core tables: core_manifest, core_rejects, core_quality
│       │   ├── manifest.py     # 🎯 WorkManifest (Option A: upsert, current-state)
│       │   ├── rejects.py      # 🎯 RejectSink (validation failures)
│       │   ├── quality.py      # 🎯 QualityRunner (quality checks)
│       │   ├── temporal.py     # WeekEnding, date ranges, windows
│       │   ├── execution.py    # ExecutionContext, lineage tracking
│       │   ├── hashing.py      # Record deduplication (MD5)
│       │   ├── idempotency.py  # Skip/force, delete+insert helpers
│       │   ├── rolling.py      # Rolling window calculations
│       │   └── storage.py      # DB-agnostic sync protocols
│       │
│       └── domains/
│           └── otc/            # 🎯 CANONICAL OTC DOMAIN (use this one!)
│               ├── __init__.py         # 🎯 Imports pipelines (triggers registration)
│               ├── schema.py           # DOMAIN="otc", Tier enum, TABLES, STAGES
│               ├── connector.py        # Parse FINRA files (parse_finra_file, parse_simple_psv)
│               ├── normalizer.py       # Validation logic (normalize_records)
│               ├── calculations.py     # 🎯 BUSINESS LOGIC (pure functions)
│               └── pipelines.py        # 🎯 PIPELINE ORCHESTRATION
│                                       #   - IngestWeekPipeline
│                                       #   - NormalizeWeekPipeline
│                                       #   - AggregateWeekPipeline
│                                       #   - RollingWeekPipeline
│                                       #   All use @register_pipeline decorator
│
└── tests/
    ├── test_dispatcher.py
    ├── test_pipelines.py
    └── domains/
        └── otc/
            └── test_otc.py             # OTC domain tests
```

---

## Canonical Entrypoints

### 1. CLI Entrypoint: How `spine` Command Resolves

**Definition**: [pyproject.toml](../pyproject.toml#L35)
```toml
[project.scripts]
spine = "market_spine.cli:main"
```

**Module**: [src/market_spine/cli.py](../src/market_spine/cli.py)

**Entry function**: `main()` - Click group

**Key commands**:
```bash
spine --version                 # Show version
spine db init                   # Initialize database (runs migrations)
spine db reset                  # Reset database
spine run <pipeline> [--params] # Run a specific pipeline
spine pipeline list             # List all registered pipelines
```

**How it works**:
1. User runs `spine run otc.ingest_week --week-ending 2025-12-26 ...`
2. CLI calls `dispatcher.dispatch_pipeline(name, params)`
3. Dispatcher calls `registry.get_pipeline(name)` to get pipeline class
4. Dispatcher instantiates and runs pipeline

### 2. Pipeline Registration: Auto-Discovery

**Registry module**: [src/market_spine/registry.py](../src/market_spine/registry.py)

**Current discovery mechanism** (line 47-68):
```python
def _load_pipelines() -> None:
    """Load all pipeline modules to trigger registration."""
    import importlib
    import pkgutil
    from pathlib import Path
    
    # ⚠️ CURRENT: Loads from market_spine/domains/
    domains_path = Path(__file__).parent / "domains"
    if domains_path.exists():
        for _, name, is_pkg in pkgutil.iter_modules([str(domains_path)]):
            if not is_pkg:
                continue
            try:
                importlib.import_module(f"market_spine.domains.{name}.pipelines")
                logger.debug("domain_pipelines_loaded", domain=name)
            except ImportError as e:
                logger.debug("domain_pipelines_not_found", domain=name, error=str(e))

_load_pipelines()  # Runs at module import time
```

**Problem**: This loads from `market_spine/domains/`, not `spine/domains/`.

**How OTC pipelines currently register**:
1. `spine/domains/otc/__init__.py` imports `pipelines` module
2. `pipelines.py` defines pipeline classes with `@register_pipeline("otc.ingest_week")`
3. **BUT** registry doesn't auto-discover `spine/domains/`
4. Pipelines only register if something imports `spine.domains.otc`

**Current workaround**: Manual import somewhere (needs to be fixed).

### 3. Database Initialization

**Module**: [src/market_spine/db.py](../src/market_spine/db.py)

**Functions**:
- `get_connection()` → Returns SQLite connection to `spine.db`
- `init_db()` → Runs SQL migrations from `migrations/*.sql`
- `reset_db()` → Drops all tables and re-runs migrations

**Migration files**:
- [migrations/001_core_executions.sql](../migrations/001_core_executions.sql) - Legacy (not used by new manifest)
- [migrations/020_otc_tables.sql](../migrations/020_otc_tables.sql) - OTC domain tables

**Core tables** (`core_manifest`, `core_rejects`, `core_quality`):
- **Not in migrations** - Created via `create_core_tables(conn)` in pipelines
- Defined in [src/spine/core/schema.py](../src/spine/core/schema.py)
- Idempotent (`CREATE TABLE IF NOT EXISTS`)

---

## Running OTC End-to-End

### Prerequisites

```powershell
# Navigate to repo
cd c:\projects\spine-core\market-spine-basic

# Activate virtual environment
.\.venv\Scripts\activate

# Set PYTHONPATH (if not using editable install)
$env:PYTHONPATH = "src"
```

### Step 1: Initialize Database

```powershell
# Method 1: Using CLI
spine db init

# Method 2: Manual migrations
sqlite3 spine.db < migrations/001_core_executions.sql
sqlite3 spine.db < migrations/020_otc_tables.sql

# Core tables (core_manifest, core_rejects, core_quality) are created
# automatically by pipelines on first run
```

### Step 2: Ingest Raw Data

```powershell
# Ingest one week of data
spine run otc.ingest_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1 \
  --file-path data/finra/nms_tier1_2026-01-02.csv

# This parses the FINRA PSV file and inserts into otc_raw table
```

### Step 3: Normalize Data

```powershell
# Validate and normalize the ingested data
spine run otc.normalize_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1

# This:
# - Reads from otc_raw
# - Validates records (symbol format, positive volumes, etc.)
# - Writes accepted records to otc_venue_volume
# - Writes rejected records to core_rejects
```

### Step 4: Aggregate Metrics

```powershell
# Compute symbol summaries and venue shares
spine run otc.aggregate_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1

# This:
# - Reads from otc_venue_volume
# - Computes symbol_summaries (total volume per symbol)
# - Computes venue_shares (market share % per venue)
# - Runs quality checks (e.g., market share sum ~= 100%)
# - Writes to otc_symbol_summary and otc_venue_share tables
```

### Step 5: Compute Rolling Metrics (Optional)

```powershell
# Compute 6-week rolling averages
spine run otc.rolling_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1

# Requires 6 prior weeks of data (2025-11-14 through 2025-12-26)
# Computes rolling average volume per symbol
```

### Step 6: Full Backfill (All Steps)

```powershell
# Run all steps for multiple weeks
spine run otc.backfill_range \
  --start 2025-11-07 \
  --end 2025-12-26 \
  --tier NMS_TIER_1 \
  --data-dir data/finra

# This runs ingest → normalize → aggregate for each week in range
```

### Step 7: Query Results

```powershell
# Option 1: Use query script
python query_otc.py

# Option 2: Direct SQL
sqlite3 spine.db "
  SELECT venue_name, market_share_pct 
  FROM otc_venue_share 
  WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
  ORDER BY market_share_pct DESC 
  LIMIT 10
"

# Option 3: Check manifest
sqlite3 spine.db "
  SELECT domain, partition_key, stage, stage_rank, row_count, updated_at
  FROM core_manifest
  WHERE domain = 'otc'
  ORDER BY updated_at DESC
"
```

### Verify Pipeline Registration

```powershell
# List all registered pipelines
spine pipeline list

# Expected output:
# otc.aggregate_week
# otc.backfill_range
# otc.ingest_week
# otc.normalize_week
# otc.rolling_week
```

---

## Where to Change Things

### 1. Add a New Calculation to OTC

**Goal**: Add a new metric (e.g., symbol volatility).

**Files to modify**:

1. **[src/spine/domains/otc/calculations.py](../src/spine/domains/otc/calculations.py)**
   - Add result dataclass: `@dataclass class SymbolVolatility`
   - Add pure function: `def compute_symbol_volatility(records) -> list[SymbolVolatility]`

2. **[migrations/020_otc_tables.sql](../migrations/020_otc_tables.sql)**
   - Add new table: `CREATE TABLE otc_symbol_volatility (...)`

3. **[src/spine/domains/otc/schema.py](../src/spine/domains/otc/schema.py)**
   - Add to `TABLES` dict: `"volatility": "otc_symbol_volatility"`

4. **[src/spine/domains/otc/pipelines.py](../src/spine/domains/otc/pipelines.py)**
   - In `AggregateWeekPipeline.run()`:
     ```python
     from spine.domains.otc.calculations import compute_symbol_volatility
     
     # Compute
     volatility = compute_symbol_volatility(normalized_records)
     
     # Write
     for v in volatility:
         conn.execute(f"INSERT INTO {TABLES['volatility']} (...) VALUES (...)", ...)
     ```

**Testing**:
```python
# tests/domains/otc/test_otc.py
def test_compute_symbol_volatility():
    records = [...]
    result = compute_symbol_volatility(records)
    assert result[0].volatility_pct > 0
```

### 2. Add a New Domain (e.g., Equity)

**Goal**: Create a new domain for equity data.

**Steps**:

1. **Create domain structure**:
   ```
   src/spine/domains/equity/
   ├── __init__.py          # Import pipelines to trigger registration
   ├── schema.py            # DOMAIN = "equity", tables, stages
   ├── connector.py         # Parse source files
   ├── normalizer.py        # Validation logic
   ├── calculations.py      # Business logic (pure functions)
   └── pipelines.py         # Pipeline orchestration
   ```

2. **Define schema** (`schema.py`):
   ```python
   DOMAIN = "equity"
   
   STAGES = ["PENDING", "INGESTED", "NORMALIZED", "AGGREGATED"]
   
   TABLES = {
       "raw": "equity_raw",
       "trades": "equity_trades",
       "summary": "equity_summary",
   }
   ```

3. **Create migrations**:
   ```sql
   -- migrations/030_equity_tables.sql
   CREATE TABLE IF NOT EXISTS equity_raw (...);
   CREATE TABLE IF NOT EXISTS equity_trades (...);
   CREATE TABLE IF NOT EXISTS equity_summary (...);
   ```

4. **Define pipelines** (`pipelines.py`):
   ```python
   from market_spine.registry import register_pipeline
   from market_spine.pipelines.base import Pipeline, PipelineResult
   
   @register_pipeline("equity.ingest_day")
   class IngestDayPipeline(Pipeline):
       name = "equity.ingest_day"
       description = "Ingest equity data for one day"
       
       def run(self) -> PipelineResult:
           # Use spine.core primitives
           manifest = WorkManifest(conn, domain=DOMAIN, stages=STAGES)
           # ... implementation ...
   ```

5. **Import in `__init__.py`**:
   ```python
   # src/spine/domains/equity/__init__.py
   from spine.domains.equity import pipelines  # noqa: F401 - registers pipelines
   ```

6. **Ensure registry discovers it**:
   - After cleanup, registry will auto-discover `spine.domains.equity`

### 3. Add a New Platform Primitive

**Goal**: Add a new cross-tier utility to `spine.core`.

**Example**: Add a `Deduplicator` primitive.

**Steps**:

1. **Create module** (`src/spine/core/deduplicator.py`):
   ```python
   """Generic record deduplication."""
   
   from typing import Protocol, Iterable, TypeVar
   from spine.core.hashing import compute_hash
   
   T = TypeVar('T')
   
   class Connection(Protocol):
       def execute(self, sql: str, params: tuple = ()) -> Any: ...
   
   class Deduplicator:
       """
       Deduplicate records against existing hashes.
       
       SYNC-ONLY: All methods are synchronous.
       """
       
       def __init__(self, conn: Connection, table: str, hash_column: str = "record_hash"):
           self.conn = conn
           self.table = table
           self.hash_column = hash_column
       
       def get_existing_hashes(self) -> set[str]:
           """Get all existing hashes from table."""
           rows = self.conn.execute(
               f"SELECT DISTINCT {self.hash_column} FROM {self.table}"
           ).fetchall()
           return {row[0] for row in rows}
       
       def is_duplicate(self, record_hash: str) -> bool:
           """Check if hash already exists."""
           row = self.conn.execute(
               f"SELECT 1 FROM {self.table} WHERE {self.hash_column} = ? LIMIT 1",
               (record_hash,)
           ).fetchone()
           return row is not None
   ```

2. **Export in `__init__.py`**:
   ```python
   # src/spine/core/__init__.py
   from spine.core.deduplicator import Deduplicator
   
   __all__ = [
       # ... existing exports ...
       "Deduplicator",
   ]
   ```

3. **Document** ([docs/architecture/CORE_PRIMITIVES.md](../../docs/architecture/CORE_PRIMITIVES.md)):
   ```markdown
   ### 9. Deduplicator (`deduplicator.py`)
   
   **Deduplicator** - Generic record deduplication.
   
   ```python
   from spine.core import Deduplicator
   
   dedup = Deduplicator(conn, table="otc_raw", hash_column="record_hash")
   existing = dedup.get_existing_hashes()
   
   for record in records:
       if record.hash not in existing:
           insert(record)
   ```
   ```

4. **Write tests**:
   ```python
   # tests/test_deduplicator.py
   def test_deduplicator():
       # ...
   ```

**Design Guidelines for New Primitives**:
- ✅ Domain-agnostic (no OTC/equity-specific logic)
- ✅ Synchronous (no async/await)
- ✅ Use protocols for DB connections
- ✅ Keep API small (≤5 public methods)
- ✅ Docstrings with examples
- ✅ Test with in-memory SQLite

---

## Key Concepts Summary

### Manifest (Option A: Current-State)

- **One row per stage** per partition (not event log)
- **UNIQUE constraint** on `(domain, partition_key, stage)`
- `advance_to()` **upserts** (creates or updates stage row)
- `get()` returns all stages for a partition in rank order
- `is_at_least()` compares stage ranks
- Future-proof for Option B (event sourcing) via optional `on_stage_change` hook

### Core Tables

**Three shared tables** (not per-domain):
1. `core_manifest` - Workflow stage tracking
2. `core_rejects` - Validation failures
3. `core_quality` - Quality check results

**Partitioning**: Each domain writes to same tables using `domain` parameter.

**Creation**: Via `create_core_tables(conn)`, not migrations.

### Domain Tables

**Per-domain tables** (e.g., OTC):
- `otc_raw` - Raw ingested records
- `otc_venue_volume` - Normalized venue data
- `otc_symbol_summary` - Symbol aggregates
- `otc_venue_share` - Market share %
- `otc_rolling_metrics` - Rolling window metrics

**Creation**: Via migrations (e.g., `020_otc_tables.sql`).

### Cross-Tier Compatibility

**Sync-only design**:
- All `spine.core` primitives use synchronous APIs
- No async/await in domain code
- Higher tiers provide sync adapters for async drivers (asyncpg)

**Same domain code runs everywhere**:
- Basic: SQLite + sync
- Intermediate: PostgreSQL + asyncpg (wrapped in sync adapter)
- Advanced: PostgreSQL + asyncpg + Celery
- Full: PostgreSQL + asyncpg + FastAPI + Celery

**Platform differences**:
- Basic: `market_spine.cli` + `dispatcher.py` + SQLite
- Intermediate: `market_spine.api` + FastAPI + PostgreSQL
- Advanced: + Celery task queue + distributed workers
- Full: + Event sourcing + CDC + real-time streaming

---

## Troubleshooting

### Pipelines Not Registering

**Problem**: `spine pipeline list` shows no pipelines.

**Causes**:
1. Registry not loading from correct path
2. Import errors in pipeline modules
3. Missing `@register_pipeline` decorators

**Solution**:
```powershell
# Check what registry is loading
python -c "
from market_spine.registry import _registry
print('Registered pipelines:', list(_registry.keys()))
"

# Manually import to check for errors
python -c "
from spine.domains.otc import pipelines
from market_spine.registry import _registry
print('OTC pipelines:', [k for k in _registry.keys() if k.startswith('otc.')])
"
```

### Database Locked

**Problem**: `database is locked` error.

**Cause**: Another process has SQLite connection open.

**Solution**:
```powershell
# Kill all Python processes
taskkill /F /IM python.exe

# Or use different database
$env:SPINE_DB_PATH = "spine_test.db"
```

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'spine'`

**Cause**: PYTHONPATH not set or package not installed.

**Solution**:
```powershell
# Set PYTHONPATH
$env:PYTHONPATH = "src"

# Or install in editable mode
pip install -e .
```

---

## Next Steps

1. **Run cleanup plan** (see separate CLEANUP_PLAN.md) to remove duplicate domain code
2. **Add tests** for new calculations/domains
3. **Update docs** when adding new primitives or domains
4. **Review cross-tier compatibility** when making changes to `spine/`

For questions or issues, see [README.md](../README.md) or check [docs/architecture/](../../docs/architecture/).
