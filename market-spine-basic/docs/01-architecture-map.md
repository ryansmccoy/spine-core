# Architecture Map — Runtime Call Paths

> Generated: January 2026 | Post Phase 1-4 Consolidation

This document describes the runtime call paths for CLI and API operations.

---

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ENTRY POINTS                                    │
├─────────────────────────────────┬───────────────────────────────────────────┤
│         CLI (Typer)             │              API (FastAPI)                │
│                                 │                                           │
│  spine run run <pipeline>       │  POST /v1/pipelines/{name}/run            │
│  spine pipelines list           │  GET /v1/pipelines                        │
│  spine query weeks              │  GET /v1/query/weeks                      │
└─────────────────────────────────┴───────────────────────────────────────────┘
                │                                   │
                │  Parse CLI args                   │  Parse JSON body
                │  (cli/params.py)                  │  (Pydantic models)
                ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          COMMAND LAYER                                       │
│                       (market_spine/app/commands/)                          │
│                                                                              │
│  RunPipelineCommand      ListPipelinesCommand      QueryWeeksCommand        │
│  DescribePipelineCommand                            QuerySymbolsCommand     │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         SERVICES                                       │ │
│  │                    (market_spine/app/services/)                        │ │
│  │                                                                        │ │
│  │  TierNormalizer  →  Normalize "tier1" → "NMS_TIER_1"                  │ │
│  │  ParameterResolver  →  Merge params, apply normalization              │ │
│  │  IngestResolver  →  Derive file path from week_ending + tier          │ │
│  │  DataSourceConfig  →  Provide table names                             │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                │
                │  Commands call framework
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FRAMEWORK LAYER                                     │
│                        (spine.framework)                                     │
│                                                                              │
│  Dispatcher.submit()  →  Creates Execution, calls Runner                    │
│  Runner.run()  →  Gets pipeline from Registry, validates params, executes   │
│  Registry  →  Lazy-loads domain pipelines on first access                   │
└─────────────────────────────────────────────────────────────────────────────┘
                │
                │  Runner instantiates pipeline
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DOMAIN LAYER                                        │
│                   (spine.domains.finra.otc_transparency)                    │
│                                                                              │
│  IngestWeekPipeline.run()  →  Parse FINRA file, insert to raw table         │
│  NormalizeWeekPipeline.run()  →  Validate, normalize, insert                │
│  AggregateWeekPipeline.run()  →  Aggregate symbol-level                     │
│                                                                              │
│  Uses: connector.py (parsing), normalizer.py (validation),                  │
│        calculations.py (aggregation), schema.py (Tier enum, TABLES)        │
└─────────────────────────────────────────────────────────────────────────────┘
                │
                │  Domain pipelines use DB
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DATABASE                                            │
│                    (SQLite via spine.framework.db)                          │
│                                                                              │
│  get_connection()  →  Returns thread-local SQLite connection                │
│  Tables: finra_otc_transparency_raw, _normalized, _aggregated               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Call Path: `spine run run <pipeline>`

### Step 1: CLI Entry

```python
# cli/commands/run.py
@app.command("run")
def run_pipeline(ctx, pipeline, param, week_ending, tier, file_path, ...):
    # 1. Parse parameters from multiple sources
    params = ParamParser.merge_params(
        param_flags=param or [],
        extra_args=tuple(ctx.args),
        week_ending=week_ending,
        tier=tier,
        file_path=file_path,
    )
```

### Step 2: Build and Execute Command

```python
    # 2. Create command and request
    command = RunPipelineCommand()
    result = command.execute(
        RunPipelineRequest(
            pipeline=pipeline,
            params=params,
            lane=lane,
            dry_run=dry_run,
            trigger_source="cli",
        )
    )
```

### Step 3: Command Orchestration

```python
# app/commands/executions.py
class RunPipelineCommand:
    def execute(self, request):
        # 3a. Normalize parameters (tier alias → canonical)
        normalized_params = self._param_resolver.resolve(request.params)
        # {"tier": "tier1"} → {"tier": "NMS_TIER_1"}
        
        # 3b. Resolve ingest source (if applicable)
        ingest_resolution = self._ingest_resolver.resolve(
            request.pipeline, normalized_params
        )
        
        # 3c. Dispatch to framework
        dispatcher = Dispatcher()
        execution = dispatcher.submit(
            pipeline=request.pipeline,
            params=normalized_params,
            lane=lane_enum,
            trigger_source=trigger_source_enum,
        )
```

### Step 4: Framework Execution

```python
# spine.framework.dispatcher
class Dispatcher:
    def submit(self, pipeline, params, ...):
        # 4a. Create execution record
        execution = Execution(id=uuid4(), pipeline=pipeline, ...)
        
        # 4b. Run via runner
        result = self._runner.run(pipeline, params, execution_id)
        
# spine.framework.runner
class PipelineRunner:
    def run(self, pipeline_name, params, execution_id):
        # 4c. Get pipeline from registry
        pipeline_cls = get_pipeline(pipeline_name)
        
        # 4d. Validate parameters
        spec = pipeline_cls.spec
        validated_params = spec.validate(params)
        
        # 4e. Execute pipeline
        pipeline = pipeline_cls()
        result = pipeline.run(**validated_params, execution_id=execution_id)
```

### Step 5: Domain Execution

```python
# spine.domains.finra.otc_transparency.pipelines
@register_pipeline("finra.otc_transparency.normalize_week")
class NormalizeWeekPipeline(Pipeline):
    def run(self, tier, week_ending, execution_id):
        conn = get_connection()
        
        # 5a. Load raw data
        raw_data = self._load_raw(conn, tier, week_ending)
        
        # 5b. Normalize records
        normalized = normalize_records(raw_data)
        
        # 5c. Insert to normalized table
        self._insert_normalized(conn, normalized)
        
        return PipelineResult(status=COMPLETED, ...)
```

---

## Tier Normalization Flow

Tier normalization happens at the **command layer**, not CLI or framework.

```
User Input          CLI                  Command Layer           Framework
─────────────────────────────────────────────────────────────────────────────
"tier1"      →   params dict   →   TierNormalizer.normalize()   →   "NMS_TIER_1"
"Tier2"      →   params dict   →   TierNormalizer.normalize()   →   "NMS_TIER_2"
"OTC"        →   params dict   →   TierNormalizer.normalize()   →   "OTC"
```

### Where Normalization Happens

| Component | Responsibility |
|-----------|----------------|
| `cli/params.py` | Merge raw params from sources (no normalization) |
| `app/services/tier.py` | `TierNormalizer.normalize()` - canonical value |
| `app/services/params.py` | `ParameterResolver.resolve()` - calls TierNormalizer |
| `app/commands/executions.py` | Calls ParameterResolver before dispatch |

### Source of Truth

Tier constants are defined in **domain layer**:

```python
# spine.domains.finra.otc_transparency.schema
TIER_VALUES = ["OTC", "NMS_TIER_1", "NMS_TIER_2"]
TIER_ALIASES = {
    "tier1": "NMS_TIER_1",
    "Tier1": "NMS_TIER_1",
    ...
}
```

`TierNormalizer` imports from domain and exposes to app layer.

---

## Ingest Resolution Flow

For ingest pipelines, file paths can be explicit or derived.

```
┌───────────────────────────────────────────────────────────────┐
│                       User Provides                           │
└───────────────────────────────────────────────────────────────┘
        │                                    │
        ▼                                    ▼
┌───────────────────┐              ┌───────────────────────────┐
│   Explicit Path   │              │   Derived from Params     │
│   --file path.csv │              │   week_ending + tier      │
└───────────────────┘              └───────────────────────────┘
        │                                    │
        ▼                                    ▼
┌───────────────────────────────────────────────────────────────┐
│                    IngestResolver.resolve()                   │
│                   (app/services/ingest.py)                    │
│                                                               │
│  if file_path in params:                                      │
│      return IngestResolution(source_type="explicit", ...)     │
│  else:                                                        │
│      path = derive_from_week_tier(week_ending, tier)          │
│      return IngestResolution(source_type="derived", ...)      │
└───────────────────────────────────────────────────────────────┘
```

---

## Query Flow (Read Path)

Queries bypass the Dispatcher (no execution tracking needed).

```
CLI: spine query weeks --tier OTC
                │
                ▼
┌────────────────────────────────────────────────────────────┐
│  QueryWeeksCommand.execute(QueryWeeksRequest(tier="OTC"))  │
│                                                            │
│  1. TierNormalizer.normalize("OTC") → "OTC"               │
│  2. DataSourceConfig.normalized_data_table → table name    │
│  3. get_connection() → SQLite connection                  │
│  4. SELECT DISTINCT week_ending FROM {table} WHERE tier=? │
│  5. Return QueryWeeksResult(weeks=[...])                  │
└────────────────────────────────────────────────────────────┘
                │
                ▼
CLI: Render Rich table with results
```

---

## API Flow

API routes use the same commands, with Pydantic at the boundary.

```python
# api/routes/v1/pipelines.py
@router.post("/v1/pipelines/{pipeline_name}/run")
async def run_pipeline(pipeline_name: str, body: RunPipelineBody):
    # 1. Build command request (from Pydantic → dataclass)
    command = RunPipelineCommand()
    result = command.execute(
        RunPipelineRequest(
            pipeline=pipeline_name,
            params=body.params,
            dry_run=body.dry_run,
            trigger_source="api",
        )
    )
    
    # 2. Convert result to Pydantic response
    if not result.success:
        raise HTTPException(...)
    
    return ExecutionResponse(
        execution_id=result.execution_id,
        status=result.status.value,
        ...
    )
```

**Key principle:** Pydantic models are used ONLY in API routes. Commands use dataclasses.
