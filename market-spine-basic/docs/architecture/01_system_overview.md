# System Overview

This document explains the two-layer architecture of Market Spine Basic and why it's structured this way.

## The Two Layers

Market Spine Basic has two distinct code layers with different purposes:

```
src/
├── market_spine/   ← Application Layer (tier-specific)
└── spine/          ← Library Layer (shareable)
```

### Application Layer: `market_spine/`

**Purpose**: The glue that makes pipelines runnable.

**Contains**:
- CLI (`cli.py`) — The `spine` command
- Dispatcher (`dispatcher.py`) — Routes execution requests
- Runner (`runner.py`) — Executes pipeline instances
- Registry (`registry.py`) — Discovers `@register_pipeline` decorators
- Database (`db.py`) — SQLite connection factory
- Configuration (`config.py`) — Environment-based settings

**Key insight**: This layer is **tier-specific**. The Intermediate tier has a different dispatcher (with Celery), the Advanced tier has a different runner (with parallelism). The **interface** is stable; the **implementation** varies.

### Library Layer: `spine/`

**Purpose**: Reusable platform primitives and domain logic.

**Contains**:
- `spine.core` — Domain-agnostic primitives
- `spine.domains.otc` — OTC-specific logic and pipelines

**Key insight**: This layer is **shareable across all tiers**. The same `spine.domains.otc.pipelines` module works unchanged in Basic, Intermediate, and Advanced.

## Why Two Layers?

The separation serves three goals:

### 1. Portability

Domain code shouldn't care *how* it's executed. The OTC pipelines don't know if they're running:
- Synchronously in Basic
- In a Celery worker in Intermediate
- In a distributed DAG in Advanced

They just define their logic and let the app layer handle execution.

### 2. Testability

Domain logic can be tested in isolation without spinning up the full app:

```python
from spine.domains.otc.calculations import compute_symbol_summaries
from spine.domains.otc.normalizer import normalize_records

# Test pure business logic
result = normalize_records(raw_records)
assert result.accepted_count == 100
```

### 3. Extraction

If the OTC domain grows complex, it can be extracted to its own package (`spine-domains-otc`) without touching the app layer.

## Layer Rules

### Rule 1: Domains Never Import from `market_spine`

❌ **Wrong**:
```python
# spine/domains/otc/pipelines.py
from market_spine.db import get_connection  # BAD!
```

✅ **Right**:
```python
# spine/domains/otc/pipelines.py
from market_spine.db import get_connection  # Connection passed in or obtained at app boundary
```

Wait, that looks the same! Here's the key: the **import is allowed** because pipelines need the connection, but **domains shouldn't contain the connection logic**. The pipeline receives the connection from the app layer context.

In practice, for simplicity in Basic tier, we allow this import. The rule is: domains should be *capable* of running without `market_spine`, even if they don't today.

### Rule 2: Business Logic in `calculations.py`

Pipelines orchestrate. Calculations compute.

❌ **Wrong**:
```python
# spine/domains/otc/pipelines.py
class AggregateWeekPipeline:
    def run(self):
        # 100 lines of aggregation SQL and logic
```

✅ **Right**:
```python
# spine/domains/otc/calculations.py
def compute_symbol_summaries(records: list[VenueVolume]) -> list[SymbolSummary]:
    """Pure function: records in, summaries out."""
    ...

# spine/domains/otc/pipelines.py
class AggregateWeekPipeline:
    def run(self):
        records = load_records(...)
        summaries = compute_symbol_summaries(records)
        save_summaries(summaries)
```

### Rule 3: Core Primitives Are Domain-Agnostic

`spine.core` knows nothing about OTC, equities, or any domain:

```python
# spine/core/manifest.py
class WorkManifest:
    def __init__(self, conn, domain: str, stages: list[str]):
        ...  # Works for any domain
```

The domain passes its name and stages when constructing primitives.

## Visual Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLI: spine run ...                          │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Dispatcher.submit(pipeline, params)             │
│                     - Sets logging context                          │
│                     - Creates Execution record                      │
│                     - Calls Runner.run()                            │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Runner.run(pipeline_name, params)               │
│                     - Resolves pipeline from Registry               │
│                     - Instantiates and runs                         │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Registry.get_pipeline(name)                     │
│                     - Returns Pipeline class                        │
│                     - Auto-loaded at import time                    │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Pipeline.run()                                  │
│                     - Uses spine.core primitives                    │
│                     - Calls domain calculations                     │
│                     - Writes to database                            │
└─────────────────────────────────────────────────────────────────────┘
```

## File Responsibilities

### Application Layer (`market_spine/`)

| File | Responsibility |
|------|----------------|
| `cli.py` | Parse commands, call dispatcher |
| `dispatcher.py` | Create Execution, set context, run pipeline, log summary |
| `runner.py` | Resolve pipeline, instantiate, call `.run()` |
| `registry.py` | Store pipeline classes, auto-discover domains |
| `db.py` | Connection factory, migrations |
| `config.py` | Read environment variables |
| `pipelines/base.py` | `Pipeline`, `PipelineResult`, `PipelineStatus` base classes |
| `logging/` | Structured logging configuration |

### Library Layer (`spine/`)

| File | Responsibility |
|------|----------------|
| `core/__init__.py` | Export all primitives |
| `core/temporal.py` | `WeekEnding` value object |
| `core/execution.py` | `ExecutionContext` for lineage |
| `core/manifest.py` | `WorkManifest` for stage tracking |
| `core/rejects.py` | `RejectSink` for validation failures |
| `core/quality.py` | `QualityRunner` for quality checks |
| `core/hashing.py` | `compute_hash()` for deduplication |
| `core/schema.py` | Core table DDL |
| `domains/otc/schema.py` | Domain constants, table names |
| `domains/otc/connector.py` | Parse FINRA files |
| `domains/otc/normalizer.py` | Validate records |
| `domains/otc/calculations.py` | Business logic (pure functions) |
| `domains/otc/pipelines.py` | Pipeline orchestration |

## Next Steps

- [Execution Model](02_execution_model.md) — How dispatch actually works
- [Pipeline Model](03_pipeline_model.md) — Anatomy of a pipeline
