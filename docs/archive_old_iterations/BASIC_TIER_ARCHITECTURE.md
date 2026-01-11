# Market Spine Basic - Architecture Guide

> **Philosophy**: Intentionally simple, synchronous, and self-contained. The basic tier demonstrates core concepts without the complexity of async workers, message queues, or microservices.

---

## Table of Contents

1. [Overview](#overview)
2. [Core Architecture](#core-architecture)
3. [Key Components](#key-components)
4. [Execution Flow](#execution-flow)
5. [OTC Plugin Integration](#otc-plugin-integration)
6. [Database Layer](#database-layer)
7. [Configuration](#configuration)
8. [CLI Interface](#cli-interface)

---

## Overview

Market Spine Basic is a **synchronous pipeline execution framework** built on:

- **SQLite** for data storage
- **Decorator-based** pipeline registration
- **Immediate execution** (no queues or workers)
- **File-based** configuration
- **Plugin architecture** via domain directories

### What It Does

```
User -> CLI -> Dispatcher -> Runner -> Pipeline -> Database
                                          ↓
                                       Result
```

All execution happens **in-process** and **synchronously**. When you run a pipeline, you wait for the result.

---

## Core Architecture

### Directory Structure

```
market-spine-basic/
├── src/market_spine/
│   ├── cli.py              # Click-based command interface
│   ├── config.py           # Pydantic settings
│   ├── db.py               # SQLite connection & migrations
│   ├── dispatcher.py       # Execution coordinator
│   ├── registry.py         # Pipeline discovery & registration
│   ├── runner.py           # Pipeline executor
│   │
│   ├── pipelines/
│   │   └── base.py         # Pipeline base class
│   │
│   └── domains/            # Plugin domains (auto-discovered)
│       ├── example/        # Built-in example domain
│       │   ├── __init__.py
│       │   └── pipelines.py
│       │
│       └── otc/            # OTC Weekly Transparency plugin
│           ├── __init__.py
│           ├── models.py
│           ├── parser.py
│           ├── normalizer.py
│           ├── calculations.py
│           └── pipelines.py
│
├── migrations/             # SQL migration files
│   ├── 001_core_executions.sql
│   └── 020_otc_tables.sql
│
└── data/                   # Data files (FINRA CSVs, etc.)
```

---

## Key Components

### 1. Pipeline Base Class

**File**: `src/market_spine/pipelines/base.py`

All pipelines inherit from this abstract base:

```python
class Pipeline(ABC):
    """Base class for all pipelines."""
    
    name: str = ""
    description: str = ""
    
    def __init__(self, params: dict[str, Any] | None = None):
        self.params = params or {}
    
    @abstractmethod
    def run(self) -> PipelineResult:
        """Execute the pipeline. Must be implemented."""
        ...
```

**Key Concepts**:
- Pipelines are **classes**, not functions
- Constructor takes `params` dictionary
- `run()` method performs the work
- Returns `PipelineResult` with status, metrics, errors

**PipelineResult**:
```python
@dataclass
class PipelineResult:
    status: PipelineStatus          # COMPLETED, FAILED, etc.
    started_at: datetime
    completed_at: datetime | None
    error: str | None
    metrics: dict[str, Any]         # Custom metrics (counts, etc.)
```

---

### 2. Registry System

**File**: `src/market_spine/registry.py`

The registry uses a **decorator pattern** for pipeline registration:

```python
@register_pipeline("example.hello")
class ExampleHelloPipeline(Pipeline):
    name = "example.hello"
    description = "A simple hello world pipeline"
    
    def run(self) -> PipelineResult:
        # Implementation
        ...
```

**How It Works**:

1. **Decorator registers** the class in a global `_registry` dict
2. **Auto-discovery** via `_load_pipelines()`:
   ```python
   # Scans src/market_spine/domains/*/pipelines.py
   for domain in domains_path:
       importlib.import_module(f"market_spine.domains.{domain}.pipelines")
   ```
3. **Lazy loading**: Modules are imported when the registry initializes

**API**:
- `register_pipeline(name)` - Decorator to register a pipeline
- `get_pipeline(name)` - Retrieve pipeline class by name
- `list_pipelines()` - List all registered pipeline names

---

### 3. Runner

**File**: `src/market_spine/runner.py`

The runner **executes pipelines synchronously**:

```python
class PipelineRunner:
    def run(self, pipeline_name: str, params: dict[str, Any]) -> PipelineResult:
        # 1. Get pipeline class from registry
        pipeline_cls = get_pipeline(pipeline_name)
        
        # 2. Instantiate with params
        pipeline = pipeline_cls(params=params)
        
        # 3. Validate parameters
        pipeline.validate_params()
        
        # 4. Execute
        result = pipeline.run()
        
        return result
```

**Characteristics**:
- **Blocking**: Waits for pipeline to complete
- **Direct execution**: No queue, no workers
- **Error handling**: Catches exceptions and returns them in `PipelineResult`

---

### 4. Dispatcher

**File**: `src/market_spine/dispatcher.py`

The dispatcher provides a **stable API** that will evolve in higher tiers:

```python
class Dispatcher:
    def submit(
        self,
        pipeline: str,
        params: dict[str, Any] | None = None,
        lane: Lane = Lane.NORMAL,              # Future: queue selection
        trigger_source: TriggerSource = ...,   # Tracking
        logical_key: str | None = None,        # Future: concurrency control
    ) -> Execution:
        # In Basic: Executes immediately
        result = self._runner.run(pipeline, params)
        
        # Wraps result in Execution record
        return execution
```

**Why It Exists**:
- **Abstraction layer** between CLI/API and execution
- **Forward compatibility**: Same API in advanced tiers (with async execution)
- **Metadata tracking**: Execution ID, trigger source, logical keys

---

### 5. Database Layer

**File**: `src/market_spine/db.py`

Simple SQLite wrapper with migration support:

```python
# Global connection (singleton)
_connection: sqlite3.Connection | None = None

def get_connection() -> sqlite3.Connection:
    """Get or create database connection."""
    if _connection is None:
        _connection = sqlite3.connect(
            settings.database_path,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode
        )
        _connection.row_factory = sqlite3.Row  # Dict-like rows
    return _connection
```

**Migration System**:
```python
def init_db():
    # 1. Create _migrations tracking table
    # 2. Scan migrations/*.sql files
    # 3. Execute any not in _migrations table
    # 4. Record executed migrations
```

**Usage in Pipelines**:
```python
conn = get_connection()
conn.execute("INSERT INTO otc_raw (...) VALUES (...)")
conn.commit()
```

---

### 6. Configuration

**File**: `src/market_spine/config.py`

Uses **Pydantic Settings** for type-safe configuration:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SPINE_",        # Environment variables start with SPINE_
        env_file=".env",            # Load from .env file
    )
    
    database_path: Path = Path("spine.db")
    data_dir: Path = Path("./data")
    log_level: Literal["DEBUG", "INFO", ...] = "INFO"
```

**Environment Variables**:
- `SPINE_DATABASE_PATH` → Sets database location
- `SPINE_DATA_DIR` → Sets data directory
- `SPINE_LOG_LEVEL` → Controls logging verbosity

---

## Execution Flow

### Complete Execution Path

```
┌─────────────────────────────────────────────────────────────┐
│ 1. CLI Entry Point                                          │
│    spine run otc.ingest -p file_path=data/file.csv         │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. CLI Handler (cli.py)                                     │
│    - Parses arguments                                       │
│    - Converts to params dict: {"file_path": "data/..."}    │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Dispatcher.submit()                                      │
│    - Creates Execution record                               │
│    - Generates execution ID                                 │
│    - Logs submission                                        │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Runner.run()                                             │
│    - Looks up pipeline in registry                          │
│    - Instantiates pipeline class                            │
│    - Calls pipeline.validate_params()                       │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Pipeline.run()                                           │
│    - Business logic executes                                │
│    - Accesses database via get_connection()                 │
│    - Processes data                                         │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Returns PipelineResult                                   │
│    - status: COMPLETED                                      │
│    - metrics: {"records": 14, "inserted": 14}               │
│    - duration calculated                                    │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. CLI Displays Result                                      │
│    ✓ Pipeline completed successfully!                       │
│      Metrics: {'records': 14, 'inserted': 14}               │
└─────────────────────────────────────────────────────────────┘
```

---

## OTC Plugin Integration

### How OTC "Plugs In"

The OTC domain demonstrates the **plugin architecture**:

```
domains/otc/
├── __init__.py              # Imports pipelines (triggers registration)
├── models.py                # Data models (RawRecord, VenueVolume, etc.)
├── parser.py                # FINRA file parsing
├── normalizer.py            # Data validation & transformation
├── calculations.py          # Aggregations (summaries, market share)
└── pipelines.py             # 3 pipelines with @register_pipeline
```

### OTC Pipelines

#### 1. **Ingest Pipeline** (`otc.ingest`)

```python
@register_pipeline("otc.ingest")
class OTCIngestPipeline(Pipeline):
    def run(self) -> PipelineResult:
        # 1. Parse FINRA CSV file
        records = list(parse_finra_file(self.params["file_path"]))
        
        # 2. Dedup via record_hash
        existing = {hash from otc_raw table}
        
        # 3. Insert new records
        for record in records:
            if record.record_hash not in existing:
                conn.execute("INSERT INTO otc_raw ...")
        
        return PipelineResult(
            status=COMPLETED,
            metrics={"records": 14, "inserted": 14}
        )
```

**What It Does**:
- Reads pipe-delimited FINRA CSV
- Generates deterministic hash for each record
- Prevents duplicate ingestion
- Stores raw data in `otc_raw` table

---

#### 2. **Normalize Pipeline** (`otc.normalize`)

```python
@register_pipeline("otc.normalize")
class OTCNormalizePipeline(Pipeline):
    def run(self) -> PipelineResult:
        # 1. Fetch unnormalized records
        raw_records = [records from otc_raw not in otc_venue_volume]
        
        # 2. Normalize (validate, parse tier, calc avg trade size)
        result = normalize_records(raw_records)
        
        # 3. Insert normalized records
        for venue_volume in result.records:
            conn.execute("INSERT INTO otc_venue_volume ...")
        
        return PipelineResult(
            status=COMPLETED,
            metrics={"accepted": 14, "rejected": 0}
        )
```

**What It Does**:
- Converts string tier to enum (e.g., "NMS Tier 1" → `Tier.NMS_TIER_1`)
- Validates data (rejects negative volumes)
- Calculates average trade size
- Stores in `otc_venue_volume` table

---

#### 3. **Summarize Pipeline** (`otc.summarize`)

```python
@register_pipeline("otc.summarize")
class OTCSummarizePipeline(Pipeline):
    def run(self) -> PipelineResult:
        # 1. Load all venue volume data
        venue_data = [all records from otc_venue_volume]
        
        # 2. Compute symbol summaries (group by symbol)
        symbols = compute_symbol_summaries(venue_data)
        
        # 3. Compute venue market shares (group by venue)
        venues = compute_venue_shares(venue_data)
        
        # 4. Store aggregations
        for summary in symbols:
            conn.execute("INSERT INTO otc_symbol_summary ...")
        
        return PipelineResult(
            status=COMPLETED,
            metrics={"symbols": 6, "venues": 5}
        )
```

**What It Does**:
- Aggregates by symbol: total volume, trade count, venue count
- Aggregates by venue: market share %, ranking
- Computes derived metrics (avg trade size)

---

### OTC Data Flow

```
FINRA CSV File
    │
    ▼
┌─────────────────┐
│  otc.ingest     │──► otc_raw table
└─────────────────┘    (batch_id, record_hash, week_ending,
                        tier, symbol, venue, mpid, volume, trades)
    │
    ▼
┌─────────────────┐
│ otc.normalize   │──► otc_venue_volume table
└─────────────────┘    (week, tier, symbol, mpid, volume,
                        trades, avg_trade_size, record_hash)
    │
    ▼
┌─────────────────┐
│ otc.summarize   │──► otc_symbol_summary table
└─────────────────┘    (week, tier, symbol, total_volume,
                        venue_count, avg_trade_size)
                    │
                    └──► otc_venue_share table
                         (week, mpid, total_volume, market_share_pct,
                          symbol_count, rank)
```

---

### Auto-Discovery Mechanism

**How OTC pipelines are discovered**:

1. **Registry initialization** (`registry.py`):
   ```python
   def _load_pipelines():
       domains_path = Path(__file__).parent / "domains"
       for domain_name in domains_path:
           # Import domain.pipelines module
           importlib.import_module(f"market_spine.domains.{domain_name}.pipelines")
   ```

2. **Domain `__init__.py`**:
   ```python
   # domains/otc/__init__.py
   from market_spine.domains.otc import pipelines  # noqa: F401
   ```
   This imports `pipelines.py`, which triggers decorator execution.

3. **Decorators execute**:
   ```python
   @register_pipeline("otc.ingest")  # ← Runs when module loads
   class OTCIngestPipeline(Pipeline):
       ...
   ```
   The decorator adds the class to `_registry["otc.ingest"]`.

**Result**: All OTC pipelines are automatically registered without manual wiring.

---

## Database Layer

### Tables Created by OTC Plugin

#### 1. `otc_raw` (Raw Ingestion)
```sql
CREATE TABLE otc_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    record_hash TEXT NOT NULL UNIQUE,  -- Deduplication key
    
    week_ending TEXT NOT NULL,         -- ISO date: "2026-01-02"
    tier TEXT NOT NULL,                -- "NMS Tier 1", "NMS Tier 2", "OTC"
    symbol TEXT NOT NULL,              -- "AAPL", "MSFT", etc.
    issue_name TEXT,                   -- Company name
    venue_name TEXT,                   -- Full venue name
    mpid TEXT NOT NULL,                -- 4-char venue code
    share_volume INTEGER NOT NULL,     -- Shares traded
    trade_count INTEGER NOT NULL,      -- Number of trades
    
    source_file TEXT,                  -- Original filename
    ingested_at TEXT DEFAULT (datetime('now'))
);
```

#### 2. `otc_venue_volume` (Normalized)
```sql
CREATE TABLE otc_venue_volume (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    share_volume INTEGER NOT NULL,
    trade_count INTEGER NOT NULL,
    avg_trade_size TEXT,               -- Decimal as text
    record_hash TEXT NOT NULL,
    
    normalized_at TEXT DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid)  -- Natural key
);
```

#### 3. `otc_symbol_summary` (Aggregated)
```sql
CREATE TABLE otc_symbol_summary (
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,      -- How many venues traded this symbol
    avg_trade_size TEXT,
    
    UNIQUE(week_ending, tier, symbol)
);
```

#### 4. `otc_venue_share` (Market Share)
```sql
CREATE TABLE otc_venue_share (
    week_ending TEXT NOT NULL,
    mpid TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    symbol_count INTEGER NOT NULL,     -- How many symbols this venue traded
    market_share_pct TEXT NOT NULL,    -- Percentage as decimal
    rank INTEGER NOT NULL,             -- 1 = highest volume
    
    UNIQUE(week_ending, mpid)
);
```

---

## Configuration

### Settings File

**Default**: `src/market_spine/config.py`

```python
class Settings(BaseSettings):
    database_path: Path = Path("spine.db")
    data_dir: Path = Path("./data")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
```

### Environment Variables

Create `.env` file:
```bash
SPINE_DATABASE_PATH=./my_custom.db
SPINE_DATA_DIR=./my_data
SPINE_LOG_LEVEL=DEBUG
```

### Accessing Settings

```python
from market_spine.config import get_settings

settings = get_settings()
print(settings.database_path)  # Path('spine.db')
```

---

## CLI Interface

### Available Commands

#### Database Management
```bash
# Initialize database (run migrations)
spine db init

# Reset database (delete + reinit)
spine db reset
```

#### Pipeline Execution
```bash
# List all registered pipelines
spine list

# Run a pipeline with parameters
spine run <pipeline-name> --param key=value

# Examples:
spine run otc.ingest -p file_path=data/finra/file.csv
spine run otc.normalize
spine run otc.summarize
spine run example.hello -p name=Alice
```

#### Interactive Shell
```bash
# Start Python REPL with context
spine shell

# Available in shell:
>>> get_connection()  # Database connection
>>> get_dispatcher()  # Dispatcher instance
>>> settings          # Configuration
```

---

## Summary: Why Basic Tier Works This Way

### Design Principles

1. **Simplicity First**
   - No async, no workers, no message queues
   - Synchronous execution is predictable
   - Easy to debug and test

2. **Self-Contained**
   - SQLite = no external database
   - Single process = no coordination overhead
   - File-based config = no config server

3. **Plugin Architecture**
   - Domains are self-contained directories
   - Auto-discovery via `pkgutil`
   - Decorator-based registration

4. **Forward Compatibility**
   - Dispatcher API stays stable
   - Higher tiers add async execution, workers, etc.
   - Basic tier code upgrades to intermediate with minimal changes

### Trade-offs

**Advantages**:
✅ Easy to understand and debug  
✅ Fast startup (no worker pool)  
✅ Portable (single SQLite file)  
✅ Perfect for development and testing  

**Limitations**:
❌ No concurrent execution  
❌ No distributed processing  
❌ Limited to single machine  
❌ Blocking operations (no async)  

### When to Use Basic Tier

- **Prototyping** new pipelines
- **Testing** business logic
- **Learning** the framework
- **Small datasets** that fit on one machine
- **CI/CD** environments (test suites)

### Evolution Path

```
Basic → Intermediate → Advanced → Full

Sync   → Async       → Celery   → Event Sourcing
SQLite → PostgreSQL  → Redis    → TimescaleDB
Direct → Repository  → Workers  → Microservices
```

The OTC plugin demonstrates this perfectly: same models and logic copied to each tier, with infrastructure evolving around them.

---

## Quick Reference

### Common Operations

**Add a new domain**:
1. Create `domains/my_domain/`
2. Add `__init__.py`, `pipelines.py`
3. Use `@register_pipeline("my_domain.my_pipeline")`
4. Restart (auto-discovered)

**Add a migration**:
1. Create `migrations/030_my_tables.sql`
2. Run `spine db init`
3. Migration auto-applies

**Run full OTC workflow**:
```bash
spine db init
spine run otc.ingest -p file_path=data/finra/file.csv
spine run otc.normalize
spine run otc.summarize
```

**Query results**:
```python
from market_spine.db import get_connection

conn = get_connection()
rows = conn.execute("SELECT * FROM otc_symbol_summary").fetchall()
```

---

That's the complete architecture of Market Spine Basic! The key insight: **deliberate simplicity** that enables learning and provides a foundation for the more sophisticated tiers.
