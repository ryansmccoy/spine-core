# Spine Core

Platform primitives for temporal data processing pipelines.

## Purpose

`spine-core` provides the foundational building blocks that all Spine tiers share:

1. **Core Primitives** (`spine.core`) — Manifest tracking, reject handling, quality checks, temporal utilities
2. **Framework** (`spine.framework`) — Pipeline execution, dispatch, registry, structured logging

This package is **tier-agnostic**: it works with SQLite (Basic), PostgreSQL (Intermediate), or distributed systems (Advanced/Full).

---

## What Lives Here

```
spine-core/
└── src/spine/
    ├── core/                    # Platform primitives (sync-only, no DB drivers)
    │   ├── manifest.py          # WorkManifest - workflow stage tracking
    │   ├── rejects.py           # RejectSink - validation failure recording
    │   ├── quality.py           # QualityRunner - quality check execution
    │   ├── temporal.py          # WeekEnding, DateRange utilities
    │   ├── execution.py         # Execution record dataclass
    │   ├── idempotency.py       # Idempotency key generation
    │   ├── hashing.py           # Content hashing utilities
    │   └── schema.py            # Core table DDL (manifest, rejects, quality)
    │
    └── framework/               # Execution framework
        ├── dispatcher.py        # Dispatcher - creates executions, routes to runner
        ├── runner.py            # PipelineRunner - validates params, runs pipelines
        ├── registry.py          # Pipeline registry with lazy loading
        ├── pipelines/           # Pipeline base classes and specs
        ├── logging/             # Structured logging (structlog-based)
        ├── params.py            # ParameterSpec validation
        ├── db.py                # Connection provider abstraction
        └── exceptions.py        # Framework exceptions
```

---

## Installation

```bash
# As a dependency (in another package's pyproject.toml)
[tool.uv.sources]
spine-core = { path = "../packages/spine-core", editable = true }

# Or directly
pip install -e packages/spine-core
```

---

## Usage

### Core Primitives

```python
from spine.core import (
    WeekEnding,
    WorkManifest,
    RejectSink,
    QualityRunner,
    create_core_tables,
)

# Validate week ending (must be Friday)
week = WeekEnding("2025-12-26")

# Track workflow stages
manifest = WorkManifest(conn, domain="finra.otc", stages=["PENDING", "INGESTED", "NORMALIZED"])
manifest.mark_complete(partition_key="2025-12-26|NMS_TIER_1", stage="INGESTED")

# Record validation failures
rejects = RejectSink(conn, domain="finra.otc", execution_id="abc-123")
rejects.record(record=bad_row, reason="Invalid symbol", severity="ERROR")

# Run quality checks
quality = QualityRunner(conn, domain="finra.otc", execution_id="abc-123")
quality.check("row_count", actual=1000, expected_min=100)
```

### Framework

```python
from spine.framework import Dispatcher, get_pipeline, list_pipelines
from spine.framework.dispatcher import Lane, TriggerSource

# List available pipelines
pipelines = list_pipelines()  # ["finra.otc_transparency.ingest_week", ...]

# Get pipeline info
pipeline_cls = get_pipeline("finra.otc_transparency.ingest_week")
print(pipeline_cls.spec)  # ParameterSpec with required/optional params

# Execute a pipeline
dispatcher = Dispatcher()
execution = dispatcher.submit(
    pipeline="finra.otc_transparency.ingest_week",
    params={"tier": "NMS_TIER_1", "week_ending": "2025-12-26", "file_path": "data.psv"},
    lane=Lane.NORMAL,
    trigger_source=TriggerSource.CLI,
)
print(execution.status)  # ExecutionStatus.COMPLETED
```

---

## Key Concepts

### Execution Model

```
Dispatcher.submit()
    │
    ├── Creates Execution record (id, batch_id, lane, trigger_source)
    │
    ├── Calls Runner.run()
    │       │
    │       ├── Gets pipeline class from Registry
    │       ├── Validates parameters against ParameterSpec
    │       └── Executes pipeline.run(**params)
    │
    └── Returns Execution with result
```

### Lanes

Executions are categorized by **lane** for prioritization:

| Lane | Use Case |
|------|----------|
| `NORMAL` | Standard real-time processing |
| `BACKFILL` | Historical data loading |
| `SLOW` | Resource-intensive operations |

### Trigger Sources

| Source | Description |
|--------|-------------|
| `CLI` | Command-line invocation |
| `API` | REST API request |
| `SCHEDULER` | Cron/scheduled job |
| `INTERNAL` | Programmatic/chained execution |

---

## Structured Logging

```python
from spine.framework.logging import get_logger, bind_execution_context

logger = get_logger(__name__)

# Bind execution context (propagates to all log calls)
bind_execution_context(
    execution_id="abc-123",
    pipeline="finra.otc_transparency.ingest_week",
    tier="NMS_TIER_1",
)

# Logs include execution context automatically
logger.info("Processing started", row_count=1000)
# → {"event": "Processing started", "row_count": 1000, "execution_id": "abc-123", ...}
```

---

## Sync-Only Design

All primitives are **synchronous**. This is intentional:

1. **Simplicity**: No async complexity in core logic
2. **Portability**: Same code works with sync or async DB drivers
3. **Testability**: Easy to test without async fixtures

Higher tiers provide sync adapters for async drivers:

```python
# Basic tier - native sync
import sqlite3
conn = sqlite3.connect("spine.db")

# Intermediate tier - async driver wrapped in sync adapter
from some_adapter import SyncPgAdapter
conn = SyncPgAdapter(asyncpg_connection)

# Same manifest code works with both!
manifest = WorkManifest(conn, domain="finra.otc", stages=STAGES)
```

---

## Layering Rules

This package follows strict layering:

- ✅ `spine.core` has NO external dependencies (except stdlib)
- ✅ `spine.framework` imports `spine.core`
- ❌ Neither imports domain code (`spine.domains.*`)
- ❌ Neither imports infrastructure (`sqlite3`, `asyncpg`, etc.)

The framework uses **dependency injection** for database connections - you provide the connection, it uses it.

---

## Development

```bash
cd packages/spine-core
uv sync
uv run pytest tests/ -v
```

---

## See Also

- [Repository README](../../README.md) — Full architecture overview
- [spine-domains](../spine-domains/README.md) — Domain implementations
- [market-spine-basic](../../market-spine-basic/README.md) — Basic tier application
