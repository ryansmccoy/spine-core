# Execution Model

This document explains how pipeline execution works: from CLI command to completed result.

## The Execution Flow

Every pipeline execution follows this path:

```
CLI → Dispatcher → Runner → Registry → Pipeline → Result
```

Let's trace a real command:

```bash
spine run otc.ingest_week -p week_ending=2025-12-26 -p tier=NMS_TIER_1 -p file_path=data/file.psv
```

### Step 1: CLI Parses the Command

**File**: `market_spine/cli.py`

```python
@main.command()
@click.argument("pipeline_name")
@click.option("--param", "-p", multiple=True)
def run(pipeline_name: str, param: tuple[str, ...], lane: str):
    # Parse key=value params
    params = parse_params(param)
    
    # Submit to dispatcher
    dispatcher = get_dispatcher()
    execution = dispatcher.submit(
        pipeline=pipeline_name,
        params=params,
        lane=Lane(lane),
        trigger_source=TriggerSource.CLI,
    )
```

The CLI's only job is to:
1. Parse command-line arguments
2. Convert them to a dict
3. Call the Dispatcher

### Step 2: Dispatcher Creates an Execution

**File**: `market_spine/dispatcher.py`

```python
def submit(self, pipeline: str, params: dict, lane: Lane, ...) -> Execution:
    # Generate unique execution ID
    execution_id = str(uuid4())
    
    # Create execution record
    execution = Execution(
        id=execution_id,
        pipeline=pipeline,
        params=params,
        status=PipelineStatus.PENDING,
        created_at=now,
    )
    
    # Set logging context (all logs will include execution_id)
    set_context(
        execution_id=execution_id,
        pipeline=pipeline,
        backend="sync",
    )
    
    log.info("execution.submitted", lane=lane.value)
```

The Dispatcher:
1. Generates a unique `execution_id`
2. Creates an `Execution` record
3. Sets the logging context
4. Logs `execution.submitted`

### Step 3: Runner Resolves and Runs the Pipeline

**File**: `market_spine/runner.py`

```python
def run(self, pipeline_name: str, params: dict) -> PipelineResult:
    # Get pipeline class from registry
    pipeline_cls = get_pipeline(pipeline_name)
    
    # Instantiate with params
    pipeline = pipeline_cls(params=params)
    
    # Validate parameters
    pipeline.validate_params()
    
    # Run the pipeline
    result = pipeline.run()
    
    return result
```

The Runner:
1. Looks up the pipeline class by name
2. Instantiates it with parameters
3. Validates parameters (optional)
4. Calls `.run()` and returns the result

### Step 4: Registry Returns the Pipeline Class

**File**: `market_spine/registry.py`

```python
# Global registry populated at import time
_registry: dict[str, type[Pipeline]] = {}

def get_pipeline(name: str) -> type[Pipeline]:
    if name not in _registry:
        raise KeyError(f"Pipeline '{name}' not found")
    return _registry[name]
```

The Registry:
1. Maintains a dict of `name → class`
2. Populated by `@register_pipeline` decorators
3. Auto-loads domain modules at import time

### Step 5: Pipeline Executes

**File**: `spine/domains/otc/pipelines.py`

```python
@register_pipeline("otc.ingest_week")
class IngestWeekPipeline(Pipeline):
    def run(self) -> PipelineResult:
        started = datetime.now()
        conn = get_connection()
        
        # Parse params
        week = WeekEnding(self.params["week_ending"])
        tier = Tier(self.params["tier"])
        
        # Do the work...
        records = parse_finra_file(file_path)
        insert_records(conn, records)
        
        # Return result
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={"records": len(records)}
        )
```

The Pipeline:
1. Gets database connection
2. Parses parameters
3. Uses `spine.core` primitives (manifest, rejects, etc.)
4. Performs the actual data processing
5. Returns a `PipelineResult`

### Step 6: Dispatcher Logs Summary

Back in the Dispatcher:

```python
    # After pipeline.run() returns
    execution.status = result.status
    execution.completed_at = result.completed_at
    
    log.info("execution.summary",
        status=execution.status.value,
        duration_ms=result.duration_seconds * 1000,
        rows_out=result.metrics.get("rows"),
    )
    
    # Clear logging context
    clear_context()
    
    return execution
```

## Key Concepts

### Execution Record

The `Execution` dataclass tracks a pipeline run:

```python
@dataclass
class Execution:
    id: str                    # Unique identifier (UUID)
    pipeline: str              # Pipeline name
    params: dict[str, Any]     # Parameters passed
    lane: Lane                 # Execution lane (normal/backfill/slow)
    trigger_source: TriggerSource  # What triggered it (cli/api/scheduler)
    status: PipelineStatus     # pending/running/completed/failed
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    result: PipelineResult | None
```

In Basic tier, executions are stored in memory (in the Dispatcher's `_executions` dict). Higher tiers persist them to the database.

### Pipeline Result

Every pipeline returns a `PipelineResult`:

```python
@dataclass
class PipelineResult:
    status: PipelineStatus
    started_at: datetime
    completed_at: datetime | None
    error: str | None
    metrics: dict[str, Any]
```

Metrics are arbitrary key-value pairs for the pipeline to report:
- `records` — Number of records processed
- `inserted` — Number of rows inserted
- `skipped` — Whether execution was skipped (idempotency)

### Logging Context

The Dispatcher sets a logging context that automatically attaches to all logs:

```python
set_context(
    execution_id="abc-123",
    pipeline="otc.ingest_week",
    backend="sync",
)
```

Now every log message includes these fields:

```
2025-12-26T10:15:32.123Z [info] ingest.parsed
    execution_id=abc-123
    pipeline=otc.ingest_week
    backend=sync
    rows=50000
```

This enables:
- Tracing all logs for one execution
- Filtering by pipeline
- Correlating logs with execution records

## Why This Design?

### Single Entry Point

All execution goes through the Dispatcher. This ensures:
- Every execution has an ID
- Logging context is always set
- Results are always captured
- Future: queueing, rate limiting, retries

### Separation of Concerns

| Component | Responsibility |
|-----------|----------------|
| CLI | Parse commands, format output |
| Dispatcher | Execution lifecycle, logging context |
| Runner | Resolve and run pipelines |
| Registry | Pipeline discovery |
| Pipeline | Business logic |

### Registry Pattern

Pipelines register themselves:

```python
@register_pipeline("otc.ingest_week")
class IngestWeekPipeline(Pipeline):
    ...
```

Benefits:
- No central manifest to maintain
- New pipelines are auto-discovered
- Pipeline name → class mapping is explicit

## In Higher Tiers

The execution model evolves:

| Tier | Dispatcher Behavior |
|------|---------------------|
| Basic | Synchronous, immediate execution |
| Intermediate | Queue to Celery, async execution |
| Advanced | DAG orchestration, parallel execution |

The **interface** (`dispatcher.submit()`) remains the same. The **implementation** changes.

## Next Steps

- [Pipeline Model](03_pipeline_model.md) — How to write a pipeline
- [Single Dispatch Entrypoint ADR](../decisions/001_single_dispatch_entrypoint.md) — Why this design
