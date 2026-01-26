# Architecture Evolution: Pipelines → Workflow Orchestration

> **Purpose**: This document explains how the spine-core architecture has evolved from direct pipeline execution to workflow-based orchestration. Use this to understand the preferred patterns when working with this codebase.

---

## Executive Summary

The codebase contains **two architectural patterns**:

| Era | Pattern | Status |
|-----|---------|--------|
| **Legacy** | Direct Pipeline Execution | Still works, but deprecated for multi-step flows |
| **Current** | Workflow Orchestration | **Preferred** for all new development |

**Key Insight**: Pipelines still exist and do the actual work. Workflows orchestrate them via `Step.pipeline()` references.

---

## 1. The Evolution

### Phase 1: Direct Pipeline Execution (Legacy)

Originally, pipelines were executed directly:

```python
# OLD PATTERN - Direct execution
class FetchPricePipeline(Pipeline):
    def run(self, context):
        data = fetch_from_api()
        validate(data)  # Mixed concerns!
        calculate(data)  # More mixed concerns!
        store(data)
        return {"rows": len(data)}

# Called directly
result = FetchPricePipeline().run({})
```

**Problems with this approach:**
- Pipelines grew into monoliths doing multiple things
- No standardized validation between steps
- Hard to track progress through stages
- Difficult to implement idempotency
- No centralized error/anomaly tracking

### Phase 2: Workflow Orchestration (Current)

Now, workflows orchestrate pipelines:

```python
# NEW PATTERN - Workflow orchestration
workflow = Workflow(
    name="price_ingestion",
    steps=[
        # Lambda: LIGHTWEIGHT validation only
        Step.lambda_("validate_params", lambda ctx: ctx.get("symbol") is not None),
        
        # Pipeline: Actual work via registry lookup
        Step.pipeline("fetch", "prices/fetch_daily"),
        
        # Lambda: Check data quality
        Step.lambda_("check_quality", lambda ctx: len(ctx.get("rows", [])) > 0),
        
        # Pipeline: More work
        Step.pipeline("calculate", "prices/calculate_metrics"),
    ]
)

# Execute via runner
result = WorkflowRunner(db_session).run(workflow, context)
```

**Benefits:**
- Clear separation of concerns
- Validation between steps
- Centralized tracking via `core_manifest`
- Error recording via `core_anomalies`
- Built-in idempotency
- Auditable execution history

---

## 2. Understanding the Architecture

### The Pipeline Registry

Pipelines are registered by name and looked up at runtime:

```python
# Registration (typically in pipeline module)
@register_pipeline("prices/fetch_daily")
class FetchDailyPricePipeline(Pipeline):
    def run(self, context):
        # Actual work happens here
        ...

# Workflow references by name (not direct import!)
Step.pipeline("fetch", "prices/fetch_daily")
#                       ↑ This is a string reference
```

### The Critical Lambda Rule

**LAMBDAS ARE LIGHTWEIGHT VALIDATION ONLY**

```python
# ✅ CORRECT - Lambda for validation
Step.lambda_("check_params", lambda ctx: ctx.get("date") is not None)
Step.lambda_("check_quality", lambda ctx: len(ctx.get("rows", [])) > 0)

# ❌ WRONG - Never put work in lambdas
Step.lambda_("fetch", lambda ctx: requests.get(...))  # NO!
Step.lambda_("calc", lambda ctx: compute_metrics(...))  # NO!
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         WORKFLOW                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   Lambda    │    │  Pipeline   │    │   Lambda    │         │
│  │  validate   │───▶│   fetch     │───▶│   check     │───▶ ... │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│        │                   │                   │                │
│        │                   │                   │                │
│        ▼                   ▼                   ▼                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    SHARED CONTEXT                         │  │
│  │  { "date": "2025-01-01", "rows": [...], "metrics": [...] }│  │
│  └──────────────────────────────────────────────────────────┘  │
│                            │                                    │
│                            ▼                                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   DATABASE TABLES                         │  │
│  │   core_manifest: Track progress, prevent duplicates       │  │
│  │   core_anomalies: Record data quality issues              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Database Tracking

### core_manifest Table

Tracks execution progress for idempotency:

```sql
CREATE TABLE core_manifest (
    capture_id TEXT PRIMARY KEY,     -- Unique execution ID
    domain TEXT NOT NULL,            -- e.g., "finra.otc"
    partition_key TEXT NOT NULL,     -- e.g., "2025-W23" or "2025-01-15"
    stage TEXT NOT NULL,             -- e.g., "INGEST", "AGGREGATE", "SCORE"
    tier TEXT NOT NULL,              -- e.g., "BRONZE", "SILVER", "GOLD"
    status TEXT NOT NULL,            -- "RUNNING", "COMPLETE", "FAILED"
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    row_count INTEGER
);
```

**Usage Pattern:**

```python
def run(self, context):
    partition_key = context["partition_key"]
    
    # 1. Check if already done (idempotency)
    if manifest.check_complete(DOMAIN, partition_key, "INGEST", "BRONZE"):
        return {"status": "SKIPPED", "reason": "Already complete"}
    
    # 2. Record start
    capture_id = manifest.record_start(DOMAIN, partition_key, "INGEST", "BRONZE")
    
    # 3. Do work
    rows = fetch_data()
    
    # 4. Record completion
    manifest.record_complete(capture_id, len(rows))
```

### core_anomalies Table

Records data quality issues without stopping execution:

```sql
CREATE TABLE core_anomalies (
    id SERIAL PRIMARY KEY,
    capture_id TEXT NOT NULL,        -- Links to manifest
    anomaly_code TEXT NOT NULL,      -- e.g., "NULL_VOLUME", "STALE_DATA"
    message TEXT,
    severity TEXT,                   -- "INFO", "WARNING", "ERROR"
    context JSONB,                   -- Additional details
    recorded_at TIMESTAMP
);
```

**Usage Pattern:**

```python
def run(self, context):
    capture_id = manifest.record_start(...)
    
    for row in source_data:
        if row.get("volume") is None:
            # Record anomaly but continue processing
            anomalies.record(
                capture_id=capture_id,
                code="NULL_VOLUME",
                message=f"Null volume for {row.get('symbol')}",
                severity="WARNING",
            )
            continue  # Skip this row
        
        valid_rows.append(row)
```

---

## 4. Migration Guide: Pipelines → Workflows

### Step 1: Identify Pipeline Stages

Look at your existing pipeline and identify logical stages:

```python
# BEFORE: Monolithic pipeline
class OldPipeline(Pipeline):
    def run(self, context):
        data = self.fetch()      # Stage 1: INGEST
        cleaned = self.clean()   # Stage 2: CLEAN  
        metrics = self.calc()    # Stage 3: CALCULATE
        self.store(metrics)      # Stage 4: STORE
```

### Step 2: Split into Focused Pipelines

Create separate pipelines for each stage:

```python
# AFTER: Focused pipelines
@register_pipeline("domain/ingest")
class IngestPipeline(Pipeline):
    def run(self, context):
        # Only fetches and stores raw data
        ...

@register_pipeline("domain/clean")
class CleanPipeline(Pipeline):
    def run(self, context):
        # Only cleans data
        ...

@register_pipeline("domain/calculate")  
class CalculatePipeline(Pipeline):
    def run(self, context):
        # Only calculates metrics
        ...
```

### Step 3: Add Database Tracking

Add manifest and anomaly tracking to each pipeline:

```python
@register_pipeline("domain/ingest")
class IngestPipeline(Pipeline):
    def run(self, context):
        partition_key = context["partition_key"]
        
        # Idempotency check
        if self.manifest.check_complete("domain", partition_key, "INGEST", "BRONZE"):
            return {"status": "SKIPPED"}
        
        capture_id = self.manifest.record_start("domain", partition_key, "INGEST", "BRONZE")
        
        try:
            rows = self.fetch_data()
            
            # Record anomalies
            for row in rows:
                if not self.validate(row):
                    self.anomalies.record(capture_id, "INVALID_ROW", str(row))
            
            # Add capture_id to all rows
            for row in rows:
                row["capture_id"] = capture_id
            
            context["raw_data"] = rows
            self.manifest.record_complete(capture_id, len(rows))
            
            return {"status": "SUCCESS", "rows": len(rows)}
            
        except Exception as e:
            self.manifest.record_failed(capture_id, str(e))
            raise
```

### Step 4: Create Workflow

Orchestrate the pipelines:

```python
workflow = Workflow(
    name="domain_processing",
    steps=[
        Step.lambda_("validate_input", lambda ctx: ctx.get("partition_key") is not None),
        Step.pipeline("ingest", "domain/ingest"),
        Step.lambda_("check_data", lambda ctx: len(ctx.get("raw_data", [])) > 0),
        Step.pipeline("clean", "domain/clean"),
        Step.pipeline("calculate", "domain/calculate"),
    ]
)
```

### Step 5: Use Provenance Tracking

Track data lineage between stages:

```python
@register_pipeline("domain/calculate")
class CalculatePipeline(Pipeline):
    def run(self, context):
        input_rows = context["clean_data"]
        
        # Extract input provenance
        input_capture_ids = {r["capture_id"] for r in input_rows}
        
        capture_id = self.manifest.record_start(...)
        
        for result in self.calculate(input_rows):
            result["capture_id"] = capture_id
            result["input_min_capture_id"] = min(input_capture_ids)
            result["input_max_capture_id"] = max(input_capture_ids)
```

---

## 5. Common Migration Mistakes

### Mistake 1: Putting Work in Lambdas

```python
# ❌ WRONG
Step.lambda_("fetch", lambda ctx: {
    "data": requests.get(ctx["url"]).json()  # This is WORK, not validation!
})

# ✅ CORRECT
Step.pipeline("fetch", "domain/fetch")  # Reference registered pipeline
```

### Mistake 2: Importing Pipeline Classes in Workflows

```python
# ❌ WRONG
from domain.pipelines import FetchPipeline
workflow = Workflow(steps=[
    Step.pipeline("fetch", FetchPipeline)  # Don't pass class!
])

# ✅ CORRECT  
workflow = Workflow(steps=[
    Step.pipeline("fetch", "domain/fetch")  # String reference
])
```

### Mistake 3: Skipping Database Tracking

```python
# ❌ WRONG - No tracking
def run(self, context):
    data = fetch()
    context["data"] = data
    return {"status": "SUCCESS"}

# ✅ CORRECT - Full tracking
def run(self, context):
    if manifest.check_complete(...):
        return {"status": "SKIPPED"}
    
    capture_id = manifest.record_start(...)
    data = fetch()
    manifest.record_complete(capture_id, len(data))
    context["data"] = data
    return {"status": "SUCCESS", "capture_id": capture_id}
```

### Mistake 4: Not Using Partition Keys

```python
# ❌ WRONG - Global/unpartitioned
manifest.check_complete("domain", "ALL", "INGEST", "BRONZE")

# ✅ CORRECT - Partitioned by time
partition_key = context.get("week_ending", "2025-W23")
manifest.check_complete("domain", partition_key, "INGEST", "BRONZE")
```

---

## 6. Quick Reference

### When to Use What

| Scenario | Use |
|----------|-----|
| Single fetch operation | Pipeline only |
| Fetch + validate + store | Workflow with 2 pipelines + lambda |
| Complex multi-stage ETL | Workflow with multiple pipelines |
| Conditional processing | Workflow with `Step.choice()` |

### The Workflow Checklist

When creating a workflow:

- [ ] Each `Step.pipeline()` references a registered pipeline by **string name**
- [ ] Each `Step.lambda_()` contains **only validation logic**
- [ ] Pipelines check `manifest.check_complete()` for idempotency
- [ ] Pipelines call `manifest.record_start()` before work
- [ ] Pipelines call `manifest.record_complete()` after work
- [ ] Data quality issues recorded to `anomalies`
- [ ] All output rows have `capture_id` field
- [ ] Aggregations track `input_min/max_capture_id`

### File Locations

```
spine-core/
├── spine/orchestration/
│   ├── workflow.py      # Workflow, Step, StepResult
│   └── runner.py        # WorkflowRunner
│
├── spine/core/
│   ├── manifest.py      # CoreManifest operations
│   └── anomalies.py     # CoreAnomalies operations
│
└── examples/patterns/
    ├── 04_workflow_with_tracking.py  # DB tracking example
    └── 08_full_domain_example.py     # Complete implementation
```

---

## 7. See Also

- [F_WORKFLOW.md](prompts/F_WORKFLOW.md) - Prompt template for implementing workflows
- [ANTI_PATTERNS.md](ANTI_PATTERNS.md) - Sections 16-19 for workflow anti-patterns
- [CONTEXT.md](CONTEXT.md) - Workflow v2 architecture overview
- `examples/patterns/` - Runnable examples demonstrating all patterns
