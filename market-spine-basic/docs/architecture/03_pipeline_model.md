# Pipeline Model

This document explains how pipelines are structured: stages, primitives, and the orchestration pattern.

## Anatomy of a Pipeline

A pipeline is a class that:
1. Inherits from `Pipeline`
2. Uses the `@register_pipeline` decorator
3. Implements the `run()` method

```python
from market_spine.pipelines.base import Pipeline, PipelineResult, PipelineStatus
from market_spine.registry import register_pipeline

@register_pipeline("domain.operation")
class MyPipeline(Pipeline):
    name = "domain.operation"
    description = "What this pipeline does"
    
    def run(self) -> PipelineResult:
        started = datetime.now()
        
        # Do the work...
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={"key": "value"}
        )
```

## The Pipeline Pattern

Every pipeline follows this pattern:

```python
def run(self) -> PipelineResult:
    started = datetime.now()
    conn = get_connection()
    
    # 1. Parse parameters
    week = WeekEnding(self.params["week_ending"])
    tier = Tier(self.params["tier"])
    force = self.params.get("force", False)
    
    # 2. Set logging context
    bind_context(domain=DOMAIN, step="my_step")
    
    # 3. Setup primitives
    manifest = WorkManifest(conn, domain=DOMAIN, stages=STAGES)
    rejects = RejectSink(conn, domain=DOMAIN, ...)
    
    # 4. Check idempotency
    if not force and manifest.is_at_least(key, "MY_STAGE"):
        return PipelineResult(status=COMPLETED, metrics={"skipped": True})
    
    # 5. Do the work (with timing)
    with log_step("operation.step1"):
        data = load_data(...)
    
    with log_step("operation.step2"):
        result = process_data(data)
    
    # 6. Write results
    with log_step("operation.save"):
        save_results(conn, result)
    
    # 7. Update manifest
    manifest.advance_to(key, "MY_STAGE", row_count=len(result))
    conn.commit()
    
    # 8. Return result
    return PipelineResult(
        status=PipelineStatus.COMPLETED,
        started_at=started,
        completed_at=datetime.now(),
        metrics={"processed": len(result)}
    )
```

## Core Primitives

Pipelines use these `spine.core` primitives:

### WorkManifest

Tracks what stage each work unit has reached:

```python
manifest = WorkManifest(conn, domain="otc", stages=["INGESTED", "NORMALIZED", "AGGREGATED"])
key = {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}

# Check if already done
if manifest.is_at_least(key, "NORMALIZED"):
    return  # Skip

# After completing work
manifest.advance_to(key, "NORMALIZED", row_count=50000)
```

### RejectSink

Records validation failures:

```python
rejects = RejectSink(conn, domain="otc", execution_id=ctx.execution_id)

# Write individual reject
rejects.write(Reject(
    record_hash="abc123",
    rule_name="INVALID_SYMBOL",
    rule_message="Symbol contains invalid characters",
    record_data={"symbol": "$$INVALID$$"},
))

# Write batch
rejects.write_batch(reject_list, partition_key=key)
```

### WeekEnding

Validated Friday dates:

```python
week = WeekEnding("2025-12-26")  # OK - Friday
week = WeekEnding("2025-12-25")  # Raises ValueError - Thursday

# Get last 3 weeks
weeks = WeekEnding.last_n(3)  # [2025-12-12, 2025-12-19, 2025-12-26]
```

### ExecutionContext

Lineage tracking:

```python
ctx = new_context(batch_id=new_batch_id("backfill"))

# ctx.execution_id = "abc-123" (auto-generated)
# ctx.batch_id = "backfill_20251226T150022_a1b2c3d4"

# Child context for sub-pipelines
child_ctx = ctx.child()
# child_ctx.parent_execution_id = "abc-123"
```

## The OTC Pipeline Set

The OTC domain has 5 pipelines that form a DAG:

```
┌─────────────────────┐
│   otc.ingest_week   │  Read FINRA file → otc_raw
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  otc.normalize_week │  otc_raw → otc_venue_volume (validated)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  otc.aggregate_week │  otc_venue_volume → otc_symbol_summary
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  otc.compute_rolling│  otc_symbol_summary → otc_rolling_metrics
└─────────────────────┘

┌─────────────────────┐
│  otc.backfill_range │  Runs ingest+normalize for multiple weeks
└─────────────────────┘
```

### Stage Progression

Each pipeline advances the manifest:

| Pipeline | Advances To | Depends On |
|----------|-------------|------------|
| `ingest_week` | `INGESTED` | (file exists) |
| `normalize_week` | `NORMALIZED` | `INGESTED` |
| `aggregate_week` | `AGGREGATED` | `NORMALIZED` |
| `compute_rolling` | `COMPUTED` | `AGGREGATED` |

### Idempotency

Running a pipeline twice with the same params:
- **Skips** if already done (unless `force=true`)
- **Same result** if forced to re-run

This is achieved by:
1. Manifest check at start
2. Delete-then-insert for data
3. Deterministic `capture_id` for lineage

## Pipeline Parameters

Parameters are passed as a dict and accessed via `self.params`:

```python
class IngestWeekPipeline(Pipeline):
    def run(self):
        week_ending = self.params["week_ending"]  # Required
        force = self.params.get("force", False)   # Optional with default
```

### Common Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `week_ending` | str | ISO Friday date (e.g., "2025-12-26") |
| `tier` | str | Data tier (e.g., "NMS_TIER_1") |
| `force` | bool | Re-run even if already done |
| `file_path` | str | Path to input file (ingest only) |
| `capture_id` | str | Explicit capture to process |

### Parameter Validation

Pipelines can validate parameters:

```python
class Pipeline(ABC):
    def validate_params(self) -> None:
        """Override to validate parameters. Raises ValueError if invalid."""
        pass
```

## Logging in Pipelines

Use structured logging with timing:

```python
from market_spine.logging import get_logger, bind_context, log_step

log = get_logger(__name__)

class MyPipeline(Pipeline):
    def run(self):
        # Set domain context
        bind_context(domain="otc", step="ingest")
        
        # Log with timing
        with log_step("ingest.parse_file", file=str(file_path)) as timer:
            records = parse_file(file_path)
            timer.add_metric("rows_parsed", len(records))
        
        # Simple log
        log.info("ingest.completed", rows=len(records))
```

## Writing a New Pipeline

### Step 1: Define the Pipeline Class

```python
# spine/domains/mydomain/pipelines.py

from market_spine.pipelines.base import Pipeline, PipelineResult, PipelineStatus
from market_spine.registry import register_pipeline

@register_pipeline("mydomain.my_operation")
class MyOperationPipeline(Pipeline):
    name = "mydomain.my_operation"
    description = "What it does"
    
    def run(self) -> PipelineResult:
        ...
```

### Step 2: Use Core Primitives

```python
from spine.core import WorkManifest, RejectSink, WeekEnding

def run(self):
    conn = get_connection()
    manifest = WorkManifest(conn, domain="mydomain", stages=["STAGE1", "STAGE2"])
    ...
```

### Step 3: Register the Domain

Ensure the pipeline module is imported at startup:

```python
# market_spine/registry.py

def _load_pipelines():
    import spine.domains.mydomain.pipelines  # Add this
```

### Step 4: Add Tests

```python
# tests/domains/mydomain/test_pipelines.py

def test_my_operation_pipeline():
    result = dispatcher.submit("mydomain.my_operation", params={...})
    assert result.status == PipelineStatus.COMPLETED
```

## Best Practices

### 1. Pipelines Orchestrate, Don't Calculate

❌ **Wrong**:
```python
def run(self):
    # 100 lines of SQL and calculation logic
```

✅ **Right**:
```python
def run(self):
    data = load_data(conn, params)
    result = compute_something(data)  # Pure function from calculations.py
    save_result(conn, result)
```

### 2. Always Update Manifest

The manifest is the source of truth for what's done:

```python
def run(self):
    # ... do work ...
    manifest.advance_to(key, "MY_STAGE", row_count=len(result))
    conn.commit()
```

### 3. Log Step Boundaries

Use `log_step` for major operations:

```python
with log_step("normalize.validate", rows_in=len(raw)):
    result = validate(raw)
    # timer automatically logs duration and metrics
```

### 4. Return Meaningful Metrics

```python
return PipelineResult(
    status=PipelineStatus.COMPLETED,
    metrics={
        "records": 50000,
        "inserted": 49500,
        "rejected": 500,
        "duration_seconds": 12.5,
    }
)
```

## Next Steps

- [Logging and Events](04_logging_and_events.md) — Structured logging details
- [Capture ID ADR](../decisions/002_capture_id_and_versioning.md) — Data provenance
