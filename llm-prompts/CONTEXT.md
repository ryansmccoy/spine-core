# Repository Context

**INJECT THIS INTO EVERY LLM SESSION**

This document contains the essential context about the Market Spine repository that every LLM agent needs to understand before making changes.

---

## Repository Structure

```
spine-core/
├── packages/
│   ├── spine-core/                    # Generic framework (AVOID CHANGES)
│   │   ├── src/spine/framework/       # Registry, pipeline base, scheduler
│   │   │   ├── registry.py            # Pipeline registry, @register_pipeline
│   │   │   ├── pipelines/             # Pipeline base class
│   │   │   ├── dispatcher.py          # Execution dispatcher
│   │   │   └── db.py                  # Database connection
│   │   └── src/spine/core/            # Core primitives
│   │       └── manifest.py            # WorkManifest, idempotency
│   │
│   └── spine-domains/                 # Domain features (PRIMARY WORKSPACE)
│       ├── src/spine/domains/
│       │   ├── finra/
│       │   │   └── otc_transparency/  # Example domain
│       │   │       ├── sources.py     # Data fetchers (file, API, etc.)
│       │   │       ├── pipelines.py   # Pipeline classes (@register_pipeline)
│       │   │       ├── calculations.py # Business logic
│       │   │       ├── validators.py  # Quality gates
│       │   │       └── schema/        # Domain schema modules
│       │   │           ├── 00_tables.sql
│       │   │           └── 02_views.sql
│       │   ├── market_data/           # Price data domain
│       │   │   ├── sources/           # Alpha Vantage, Polygon, etc.
│       │   │   ├── pipelines.py       # market_data.ingest_prices
│       │   │   └── schema/            # Price tables
│       │   └── reference/             # Reference data domains
│       ├── tests/                     # Domain tests
│       └── docs/                      # Domain documentation
│
├── market-spine-basic/                # Basic tier application
│   └── src/market_spine/
│       ├── api/                       # FastAPI routes
│       ├── cli/                       # Typer CLI commands
│       └── app/
│           ├── commands/              # Command handlers (thin adapters)
│           └── services/              # Business logic services
│
├── market-spine-intermediate/         # Intermediate tier (adds async, queues)
├── market-spine-full/                 # Full tier (adds K8s, multi-tenant)
│
├── trading-desktop/                   # React UI (API-driven only)
│   └── src/
│
└── llm-prompts/                       # This folder (LLM guidance)
```

---

## Architecture Layers

| Layer | Location | Purpose | Modification Rules |
|-------|----------|---------|-------------------|
| **Core** | `packages/spine-core/` | Generic framework | ❌ AVOID - need 2+ domains + escalation |
| **Domains** | `packages/spine-domains/` | Domain-specific logic | ✅ PRIMARY WORKSPACE |
| **App Tiers** | `market-spine-{tier}/` | CLI, API, services | ⚠️ Thin adapters only |
| **UI** | `trading-desktop/` | React frontend | ⚠️ API-driven, no direct DB |

### Layer Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                    trading-desktop (UI)                      │
│                    API calls only, no DB                     │
└─────────────────────────────────────────────────────────────┘
                              ↓ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────┐
│              market-spine-{tier} (App Adapters)              │
│         CLI → dispatches to pipelines (no logic here)        │
│         API → queries DB, triggers pipelines                 │
└─────────────────────────────────────────────────────────────┘
                              ↓ spine run {pipeline}
┌─────────────────────────────────────────────────────────────┐
│                 spine-domains (Business Logic)               │
│     Sources → fetch raw data from external systems           │
│     Pipelines → orchestrate ingestion/processing             │
│     Calculations → business logic (pure functions)           │
│                   YOUR PRIMARY WORKSPACE                     │
└─────────────────────────────────────────────────────────────┘
                              ↓ Inheritance/Registry
┌─────────────────────────────────────────────────────────────┐
│                  spine-core (Framework)                      │
│              Base classes, registries, dispatcher            │
│                      AVOID CHANGES                           │
└─────────────────────────────────────────────────────────────┘
```

### Key Pattern: Pipelines (NOT Commands) for Ingestion

**DO:** Put data ingestion logic in registered pipelines:
```python
# spine-domains/src/spine/domains/market_data/pipelines.py
@register_pipeline("market_data.ingest_prices")
class IngestPricesPipeline(Pipeline):
    def run(self):
        source = create_source()           # Get configured source
        data, anomalies = source.fetch()   # Fetch from external API
        # ... insert to database
```

**DON'T:** Create standalone CLI commands with ingestion logic:
```python
# ❌ WRONG: market-spine-basic/src/market_spine/app/commands/fetch_prices.py
# This bypasses the pipeline framework and dispatcher
```

The CLI just invokes registered pipelines:
```bash
spine run run market_data.ingest_prices -p symbol=AAPL
```

---

## Orchestration: Workflow v2

For multi-step operations with validation between steps, use the **Workflow** system.

**Location**: `packages/spine-core/src/spine/orchestration/`

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Workflow: "finra.weekly_refresh"                            │
│    Step.pipeline("ingest", "finra.otc.ingest_week")          │ ← References registered pipeline
│    Step.lambda_("validate", check_record_count)              │ ← Lightweight validation
│    Step.pipeline("normalize", "finra.otc.normalize_week")    │ ← References registered pipeline
└─────────────────────────────────────────────────────────────┘
                              ↓ looks up by name
┌─────────────────────────────────────────────────────────────┐
│  Spine Registry: Pipeline classes by name                    │
│    "finra.otc.ingest_week" → IngestWeekPipeline             │
│    "finra.otc.normalize_week" → NormalizeWeekPipeline       │
└─────────────────────────────────────────────────────────────┘
                              ↓ executes
┌─────────────────────────────────────────────────────────────┐
│  Pipelines: Do the actual work                               │
│  (Sources → Transform → Write to DB → Update core_manifest)  │
└─────────────────────────────────────────────────────────────┘
```

### When to Use

| Scenario | Use |
|----------|-----|
| Single operation (fetch, transform, calculate) | Pipeline only |
| Multiple steps with validation between them | Workflow + Pipelines |
| Need quality gates before continuing | Workflow with lambda steps |
| Need data passing between steps | Workflow with context |
| Need observability per step | Workflow |

### Step Types

```python
from spine.orchestration import Workflow, Step, StepResult

# 1. Pipeline step - references registered pipeline
Step.pipeline("ingest", "finra.otc.ingest_week")

# 2. Lambda step - lightweight validation only
def validate_records(ctx, config):
    count = ctx.get_output("ingest", "row_count", 0)
    if count < 100:
        return StepResult.fail("Too few records", "QUALITY_GATE")
    return StepResult.ok()

Step.lambda_("validate", validate_records)

# 3. Choice step - conditional branching (Intermediate tier)
Step.choice("route",
    condition=lambda ctx: ctx.params.get("full_refresh"),
    then_step="full_ingest",
    else_step="incremental_ingest",
)
```

### Critical Pattern: Lambdas are LIGHTWEIGHT

**Lambda steps should only:**
- ✅ Check record counts
- ✅ Validate outputs from previous step
- ✅ Route to different paths
- ✅ Log/notify

**Lambda steps should NOT:**
- ❌ Contain business logic
- ❌ Fetch data
- ❌ Transform data
- ❌ Write to database
- ❌ Duplicate pipeline logic

### Example Workflow

```python
from spine.orchestration import Workflow, Step, StepResult

def check_quality(ctx, config):
    """Lambda: Validate ingest quality before normalize."""
    metrics = ctx.get_output("ingest", "metrics", {})
    if metrics.get("error_rate", 0) > 0.05:
        return StepResult.fail("Error rate too high", "QUALITY_GATE")
    return StepResult.ok(output={"validated": True})

workflow = Workflow(
    name="finra.weekly_refresh",
    domain="finra.otc_transparency",
    steps=[
        Step.pipeline("ingest", "finra.otc_transparency.ingest_week"),
        Step.lambda_("validate", check_quality),
        Step.pipeline("normalize", "finra.otc_transparency.normalize_week"),
        Step.pipeline("aggregate", "finra.otc_transparency.aggregate_week"),
    ],
)

# Execute
from spine.orchestration import WorkflowRunner
runner = WorkflowRunner()
result = runner.execute(workflow, params={"week_ending": "2025-01-09", "tier": "NMS_TIER_1"})
```

### Tracking Workflow Execution

Use `core_manifest` to track workflow progress:

```python
from spine.core.manifest import WorkManifest

manifest = WorkManifest(
    conn,
    domain="workflow.finra.weekly_refresh",
    stages=["STARTED", "INGESTED", "VALIDATED", "NORMALIZED", "COMPLETED"]
)

# After workflow completes
manifest.advance_to(
    key={"week_ending": "2025-01-09", "tier": "NMS_TIER_1"},
    stage="COMPLETED",
    execution_id=result.run_id,
    step_count=len(result.completed_steps),
    duration_seconds=result.duration_seconds,
)

---

## Core Tables (Owned by spine-core)

**DO NOT modify these schemas. Write to them, don't alter them.**

### core_manifest
Tracks capture lineage for every pipeline output.

```sql
CREATE TABLE core_manifest (
    capture_id TEXT PRIMARY KEY,      -- Unique identifier for this capture
    domain TEXT NOT NULL,             -- e.g., 'finra.otc_transparency'
    stage TEXT NOT NULL,              -- e.g., 'INGEST', 'NORMALIZE', 'ROLLING'
    partition_key TEXT NOT NULL,      -- e.g., '2026-01-09|NMS_TIER_1'
    captured_at TEXT NOT NULL,        -- ISO timestamp
    status TEXT NOT NULL,             -- 'pending', 'complete', 'failed'
    row_count INTEGER,
    metadata TEXT,                    -- JSON blob
    execution_id TEXT,
    batch_id TEXT
);
```

### core_anomalies
Records errors, warnings, and quality issues.

```sql
CREATE TABLE core_anomalies (
    anomaly_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,             -- e.g., 'finra.otc_transparency'
    stage TEXT NOT NULL,              -- e.g., 'ROLLING'
    partition_key TEXT NOT NULL,      -- e.g., '2026-01-09|NMS_TIER_1'
    severity TEXT NOT NULL,           -- 'DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'
    category TEXT NOT NULL,           -- 'QUALITY_GATE', 'NETWORK', 'DATA_QUALITY', 'VALIDATION'
    message TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    metadata TEXT,                    -- JSON blob with details
    resolved_at TEXT                  -- NULL if unresolved
);
```

### core_data_readiness
Tracks data availability for scheduling and quality gates.

```sql
CREATE TABLE core_data_readiness (
    domain TEXT NOT NULL,
    stage TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    week_ending TEXT NOT NULL,
    is_ready INTEGER NOT NULL,        -- 0 or 1
    checked_at TEXT NOT NULL,
    PRIMARY KEY (domain, stage, partition_key, week_ending)
);
```

### core_expected_schedules
Defines when data should arrive.

```sql
CREATE TABLE core_expected_schedules (
    domain TEXT NOT NULL,
    stage TEXT NOT NULL,
    expected_day_of_week INTEGER,     -- 0=Monday, 6=Sunday
    expected_time TEXT,               -- HH:MM
    tolerance_hours INTEGER,
    PRIMARY KEY (domain, stage)
);
```

### core_calc_dependencies
Tracks calculation DAG for ordering.

```sql
CREATE TABLE core_calc_dependencies (
    calc_id TEXT NOT NULL,
    depends_on_calc_id TEXT NOT NULL,
    PRIMARY KEY (calc_id, depends_on_calc_id)
);
```

---

## Non-Negotiable Patterns

### 1. Registry-Driven Extensibility

```python
# Location: spine.framework.registry

# Registering a new pipeline
from spine.framework.registry import PIPELINES

@PIPELINES.register("compute_rolling")
class ComputeRollingPipeline(Pipeline):
    ...

# Using the registry
pipeline_cls = PIPELINES.get("compute_rolling")
pipeline = pipeline_cls(params)
pipeline.run()
```

**Available registries:**
- `CALCS` - Calculation classes
- `SOURCES` - Data source classes  
- `PIPELINES` - Pipeline classes

### 2. Capture ID Contract

Every pipeline output MUST include:

```python
# Required columns in every output table
capture_id TEXT NOT NULL,     # Unique per run: f"{domain}.{stage}.{partition}.{timestamp}"
captured_at TEXT NOT NULL,    # ISO timestamp of capture
execution_id TEXT,            # Groups related runs
batch_id TEXT                 # Groups batch operations
```

**Capture ID format:**
```python
capture_id = f"finra.otc_transparency.ROLLING.2026-01-09|NMS_TIER_1.20260104T143022Z"
#             └──────domain───────────┘ └stage┘ └──partition_key────┘ └timestamp──┘
```

### 3. Idempotency Pattern

```python
# Same capture_id should UPDATE, not duplicate
def write_output(conn, rows, capture_id):
    # Option A: DELETE + INSERT
    conn.execute("DELETE FROM output_table WHERE capture_id = ?", (capture_id,))
    conn.executemany("INSERT INTO output_table ...", rows)
    
    # Option B: UPSERT (SQLite)
    conn.executemany("""
        INSERT INTO output_table (capture_id, ...) VALUES (?, ...)
        ON CONFLICT (capture_id, ...) DO UPDATE SET ...
    """, rows)
```

### 4. Determinism Contract

```python
# Same inputs → same outputs (excluding audit fields)
AUDIT_FIELDS = ["captured_at", "batch_id", "execution_id"]

def assert_deterministic(result1, result2):
    for field in AUDIT_FIELDS:
        del result1[field]
        del result2[field]
    assert result1 == result2
```

### 5. Error Surfacing

```python
# NEVER swallow errors silently
def process_item(item):
    try:
        return do_work(item)
    except ValidationError as e:
        record_anomaly(
            domain="finra.otc_transparency",
            stage="NORMALIZE",
            partition_key=f"{item.week}|{item.tier}",
            severity="ERROR",
            category="VALIDATION",
            message=str(e),
            metadata={"item_id": item.id}
        )
        return None  # Allow partial success
```

### 6. Schema Module Pattern

```
# Schema files are numbered for ordering:
schema/
├── 00_tables.sql      # Tables first
├── 01_indexes.sql     # Indexes second
└── 02_views.sql       # Views last (depend on tables)

# Build process:
python scripts/build_schema.py  # Combines all → schema.sql
```

### 7. Quality Gate Pattern

```python
# Validate BEFORE compute
def run(self):
    # 1. Check preconditions
    ok, missing = require_history_window(
        conn, table, week_ending, window_weeks=6, tier=tier
    )
    
    if not ok:
        record_anomaly(severity="ERROR", category="QUALITY_GATE", ...)
        return {"status": "skipped", "reason": "insufficient_history"}
    
    # 2. Proceed with compute
    results = self.compute(...)
    return {"status": "complete", "rows": len(results)}
```

---

## Domain Example: finra.otc_transparency

### Tables (owned by domain)

```sql
-- Raw ingested data
finra_otc_transparency_venue_volume

-- Normalized per-symbol summary
finra_otc_transparency_symbol_summary

-- Rolling 6-week averages
finra_otc_transparency_symbol_rolling_6w
```

### Pipelines

| Pipeline | Stage | Description |
|----------|-------|-------------|
| `IngestWeekPipeline` | INGEST | Fetch raw PSV files from FINRA |
| `NormalizeWeekPipeline` | NORMALIZE | Dedupe, validate, create venue_volume |
| `AggregateWeekPipeline` | AGGREGATE | Aggregate to symbol_summary |
| `ComputeRollingPipeline` | ROLLING | Compute 6-week rolling averages |

### Quality Gates

| Gate | Location | Purpose |
|------|----------|---------|
| `require_history_window()` | validators.py | Enforce consecutive weeks |
| `get_symbols_with_sufficient_history()` | validators.py | Filter symbols by history |

---

## Quick Reference: File Locations

| What | Where |
|------|-------|
| Add new source | `spine-domains/src/spine/domains/{domain}/sources/{name}.py` |
| Add new pipeline | `spine-domains/src/spine/domains/{domain}/pipelines.py` |
| Add quality gate | `spine-domains/src/spine/domains/{domain}/validators.py` |
| Add domain table | `spine-domains/src/spine/domains/{domain}/schema/00_tables.sql` |
| Add domain view | `spine-domains/src/spine/domains/{domain}/schema/02_views.sql` |
| Add tests | `spine-domains/tests/{domain}/test_{feature}.py` |
| Add docs | `spine-domains/docs/{FEATURE}.md` |

---

## Next Steps

1. Read [MASTER_PROMPT.md](MASTER_PROMPT.md) for general feature implementation
2. Pick a specialized prompt from [prompts/](prompts/) if applicable
3. Check [ANTI_PATTERNS.md](ANTI_PATTERNS.md) before implementing
4. Validate against [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) when complete
