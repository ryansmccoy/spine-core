# Integration Flow

> **Purpose:** Show end-to-end data flow from core modules through API to frontend.
> **Tier:** All
> **Last Updated:** 2026-01-11

---

## Overview

This document traces how data flows through the platform stack:

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Frontend   │◄──│     API      │◄──│  Framework   │◄──│    Core      │
│   (React)    │   │   (FastAPI)  │   │ (Pipelines)  │   │  (Database)  │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

---

## Architecture Layers

### Layer 1: Core (`spine.core`)

**Responsibility:** Data types, storage, errors

**Modules:**
- `spine.core.types` - Base dataclasses (ExecutionContext, WorkManifest)
- `spine.core.storage` - Database adapters (SQLite, PostgreSQL, DB2)
- `spine.core.errors` - Structured error types

**Data Flow:**
```python
# Core provides database connection
from spine.core.storage import create_adapter, DatabaseConfig

config = DatabaseConfig.from_env()  # Reads SPINE_DB_URL
adapter = create_adapter(config)     # Returns appropriate adapter
adapter.connect()

# Core provides type definitions
from spine.core.types import ExecutionContext

context = ExecutionContext(
    execution_id="exec-123",
    domain="finra",
    params={"tier": "T1"},
)
```

---

### Layer 2: Framework (`spine.framework`)

**Responsibility:** Business logic, sources, pipelines, alerts

**Modules:**
- `spine.framework.sources` - Source protocol implementations
- `spine.framework.pipelines` - Pipeline base and registry
- `spine.framework.quality` - Quality checks
- `spine.framework.alerts` - Alert channels

**Data Flow:**
```python
# Framework uses Core for storage
from spine.core.storage import create_adapter
from spine.framework.sources import HttpSource

# Fetch data from external source
source = HttpSource(
    name="finra_otc",
    base_url="https://api.finra.org",
    auth={"api_key": os.environ["FINRA_API_KEY"]},
)
result = source.fetch("/otc/transparency/weekly")

# Framework uses Core for errors
from spine.core.errors import SourceError, TransientError

if not result.success:
    if result.error and "timeout" in result.error.lower():
        raise TransientError("FINRA API timeout")
    raise SourceError(f"FINRA API error: {result.error}")
```

---

### Layer 3: Orchestration (`spine.orchestration`)

**Responsibility:** Workflow execution, scheduling, history

**Modules:**
- `spine.orchestration.v2` - Workflow, Step, WorkflowRunner
- `spine.orchestration.scheduler` - Cron scheduling
- `spine.orchestration.history` - Run persistence

**Data Flow:**
```python
# Orchestration coordinates Framework components
from spine.orchestration.v2 import Workflow, WorkflowContext, WorkflowRunner
from spine.orchestration.history import HistoryTracker, HistoryStore
from spine.orchestration.scheduler import SchedulerService

# Define workflow using Framework pipelines
workflow = Workflow(
    name="finra_ingest",
    steps=[
        Step.lambda_("fetch", fetch_from_finra),
        Step.pipeline("transform", "finra.transform"),
        Step.lambda_("load", load_to_database),
    ],
)

# Runner uses history tracker
store = HistoryStore(adapter)
tracker = HistoryTracker(store)
runner = WorkflowRunner(registry, tracker)

# Execute with tracking
result = runner.run(workflow, params={"tier": "T1"})
```

---

### Layer 4: Domains (`spine.domains`)

**Responsibility:** Domain-specific pipelines and business logic

**Modules:**
- `spine.domains.finra` - FINRA OTC transparency
- `spine.domains.pricing` - Price data ingestion

**Data Flow:**
```python
# Domains define specific implementations
from spine.domains.finra.otc_transparency.pipelines import IngestWeekPipeline

pipeline = IngestWeekPipeline(context, {
    "tier": "T1",
    "week_ending": "2025-01-10",
})
result = pipeline.run()

# Domains use Framework sources
from spine.framework.sources import get_source

source = get_source("finra.otc_transparency")
data = source.fetch(params)
```

---

### Layer 5: API (`spine.api`)

**Responsibility:** REST endpoints, request/response handling

**Modules:**
- `spine.api.pipelines` - Pipeline execution endpoints
- `spine.api.scheduler` - Schedule management
- `spine.api.history` - Execution history
- `spine.api.health` - Health checks

**Data Flow:**
```python
# api/pipelines.py
from fastapi import APIRouter, BackgroundTasks

router = APIRouter(prefix="/pipelines")

@router.post("/run/{pipeline_name}")
async def run_pipeline(
    pipeline_name: str,
    params: dict,
    background_tasks: BackgroundTasks,
    runner: WorkflowRunner = Depends(get_runner),
) -> dict:
    """Execute a pipeline."""
    
    # Create execution ID
    execution_id = str(uuid.uuid4())[:8]
    
    # Run in background
    background_tasks.add_task(
        runner.run_pipeline,
        pipeline_name,
        params,
        execution_id=execution_id,
    )
    
    return {
        "execution_id": execution_id,
        "status": "started",
        "pipeline": pipeline_name,
    }


@router.get("/status/{execution_id}")
async def get_status(
    execution_id: str,
    store: HistoryStore = Depends(get_store),
) -> dict:
    """Get pipeline execution status."""
    
    run = store.get_workflow_run(execution_id)
    if not run:
        raise HTTPException(404, "Execution not found")
    
    steps = store.get_step_runs(execution_id)
    
    return {
        "execution_id": execution_id,
        "status": run.status.value,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "steps": [
            {
                "name": s.step_name,
                "status": s.status.value,
                "duration": s.duration_seconds,
            }
            for s in steps
        ],
        "error": run.error,
    }
```

---

### Layer 6: Frontend (`trading-desktop`)

**Responsibility:** User interface, visualization

**Modules:**
- `src/api/` - API client
- `src/components/` - React components
- `src/hooks/` - Data fetching hooks

**Data Flow:**
```typescript
// api/pipelineApi.ts
import { apiClient } from './client';

export interface PipelineStatus {
  execution_id: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  started_at: string | null;
  completed_at: string | null;
  steps: StepStatus[];
  error: string | null;
}

export const pipelineApi = {
  run: (pipelineName: string, params: Record<string, unknown>) =>
    apiClient.post<{ execution_id: string }>(`/pipelines/run/${pipelineName}`, params),
  
  getStatus: (executionId: string) =>
    apiClient.get<PipelineStatus>(`/pipelines/status/${executionId}`),
  
  listRuns: (params?: { status?: string; limit?: number }) =>
    apiClient.get<PipelineStatus[]>('/history/runs', { params }),
};


// hooks/usePipelineStatus.ts
import { useQuery } from '@tanstack/react-query';
import { pipelineApi } from '../api/pipelineApi';

export function usePipelineStatus(executionId: string) {
  return useQuery({
    queryKey: ['pipeline-status', executionId],
    queryFn: () => pipelineApi.getStatus(executionId),
    refetchInterval: (data) => 
      data?.status === 'RUNNING' ? 2000 : false,  // Poll while running
  });
}


// components/PipelineStatusCard.tsx
import { usePipelineStatus } from '../hooks/usePipelineStatus';

export function PipelineStatusCard({ executionId }: { executionId: string }) {
  const { data: status, isLoading, error } = usePipelineStatus(executionId);
  
  if (isLoading) return <Spinner />;
  if (error) return <ErrorBanner error={error} />;
  
  return (
    <Card>
      <CardHeader>
        <StatusBadge status={status.status} />
        <span>Execution: {executionId}</span>
      </CardHeader>
      <CardContent>
        <StepTimeline steps={status.steps} />
        {status.error && <ErrorMessage>{status.error}</ErrorMessage>}
      </CardContent>
    </Card>
  );
}
```

---

## Complete Flow Example: FINRA Ingestion

### 1. User Triggers (Frontend)

```typescript
// User clicks "Run Ingestion" button
const handleRunIngestion = async () => {
  const result = await pipelineApi.run('finra.otc_transparency.ingest_week', {
    tier: 'T1',
    week_ending: '2025-01-10',
  });
  
  setExecutionId(result.execution_id);
  navigate(`/pipelines/${result.execution_id}`);
};
```

### 2. API Receives Request

```python
# POST /pipelines/run/finra.otc_transparency.ingest_week
@router.post("/run/{pipeline_name}")
async def run_pipeline(pipeline_name: str, params: dict):
    execution_id = generate_id()
    
    # Queue for background execution
    background_tasks.add_task(
        execute_pipeline,
        pipeline_name,
        params,
        execution_id,
    )
    
    return {"execution_id": execution_id, "status": "started"}
```

### 3. Orchestration Executes

```python
async def execute_pipeline(name: str, params: dict, execution_id: str):
    # Get pipeline from registry
    pipeline_cls = get_pipeline(name)
    
    # Create context
    context = ExecutionContext(
        execution_id=execution_id,
        domain="finra",
        params=params,
    )
    
    # Track execution
    with tracker.track_workflow(name, domain="finra", params=params) as run:
        
        # Step 1: Fetch from FINRA
        with run.track_step("fetch", "lambda") as step:
            source = get_source("finra.otc_transparency")
            result = source.fetch({
                "tier": params["tier"],
                "week_ending": params["week_ending"],
            })
            step.record_records(len(result.records))
        
        # Step 2: Transform
        with run.track_step("transform", "lambda") as step:
            records = transform(result.records)
            step.record_records(len(records))
        
        # Step 3: Quality Check
        with run.track_step("quality", "pipeline") as step:
            passed, metrics = run_quality_checks(records)
            step.record_quality(passed, metrics)
            
            if not passed:
                # Send alert
                alerts.send(Alert(
                    severity="WARNING",
                    title="Quality Check Failed",
                    message=f"FINRA ingest failed quality: {metrics}",
                    source=name,
                    execution_id=execution_id,
                ))
                raise ValidationError("Quality check failed")
        
        # Step 4: Load
        with run.track_step("load", "lambda") as step:
            inserted = load_records(adapter, records)
            step.record_records(inserted)
        
        run.record_metric("total_records", len(records))
```

### 4. Database Updated

```sql
-- workflow_runs table
INSERT INTO workflow_runs 
    (run_id, workflow_name, domain, status, params, ...)
VALUES 
    ('exec-abc', 'finra.otc_transparency.ingest_week', 'finra', 'COMPLETED', ...);

-- workflow_step_runs table
INSERT INTO workflow_step_runs
    (step_id, run_id, step_name, status, records_processed, ...)
VALUES
    ('exec-abc-1', 'exec-abc', 'fetch', 'COMPLETED', 1500, ...),
    ('exec-abc-2', 'exec-abc', 'transform', 'COMPLETED', 1500, ...),
    ('exec-abc-3', 'exec-abc', 'quality', 'COMPLETED', 1500, ...),
    ('exec-abc-4', 'exec-abc', 'load', 'COMPLETED', 1500, ...);

-- fact_bond_trade_activity (domain table)
INSERT INTO fact_bond_trade_activity
    (week_ending, tier, cusip, volume_total, ...)
VALUES
    ('2025-01-10', 'T1', 'CUSIP123', 1000000, ...),
    ...;
```

### 5. Frontend Polls Status

```typescript
// usePipelineStatus polls every 2 seconds while RUNNING
const { data: status } = usePipelineStatus(executionId);

// When COMPLETED, show success
if (status.status === 'COMPLETED') {
  toast.success(`Processed ${status.metrics.total_records} records`);
}
```

### 6. Frontend Displays Results

```typescript
// Query the loaded data
const { data: tradeData } = useQuery({
  queryKey: ['trade-activity', weekEnding, tier],
  queryFn: () => finraApi.getTradeActivity({ weekEnding, tier }),
  enabled: status?.status === 'COMPLETED',
});

// Render in chart
<TradeActivityChart data={tradeData} />
```

---

## Sequence Diagram

```
┌─────────┐    ┌─────────┐    ┌──────────────┐    ┌───────────┐    ┌──────────┐    ┌────────┐
│ Frontend│    │   API   │    │ Orchestration │    │ Framework │    │  Source  │    │Database│
└────┬────┘    └────┬────┘    └──────┬───────┘    └─────┬─────┘    └────┬─────┘    └───┬────┘
     │              │                │                  │               │              │
     │ POST /run    │                │                  │               │              │
     │─────────────►│                │                  │               │              │
     │              │                │                  │               │              │
     │  {exec_id}   │                │                  │               │              │
     │◄─────────────│                │                  │               │              │
     │              │                │                  │               │              │
     │              │ execute()      │                  │               │              │
     │              │───────────────►│                  │               │              │
     │              │                │                  │               │              │
     │              │                │ track_workflow() │               │              │
     │              │                │─────────────────────────────────────────────────►│
     │              │                │                  │               │              │
     │              │                │ fetch()          │               │              │
     │              │                │─────────────────►│               │              │
     │              │                │                  │               │              │
     │              │                │                  │ HTTP GET      │              │
     │              │                │                  │──────────────►│              │
     │              │                │                  │               │              │
     │              │                │                  │   records     │              │
     │              │                │                  │◄──────────────│              │
     │              │                │                  │               │              │
     │              │                │    records       │               │              │
     │              │                │◄─────────────────│               │              │
     │              │                │                  │               │              │
     │              │                │ transform()      │               │              │
     │              │                │─────────────────►│               │              │
     │              │                │◄─────────────────│               │              │
     │              │                │                  │               │              │
     │              │                │ load()           │               │              │
     │              │                │─────────────────────────────────────────────────►│
     │              │                │                  │               │              │
     │ GET /status  │                │                  │               │              │
     │─────────────►│                │                  │               │              │
     │              │                │                  │               │              │
     │              │ query history  │                  │               │              │
     │              │───────────────────────────────────────────────────────────────────►
     │              │                │                  │               │              │
     │              │◄───────────────────────────────────────────────────────────────────
     │              │                │                  │               │              │
     │  {status}    │                │                  │               │              │
     │◄─────────────│                │                  │               │              │
     │              │                │                  │               │              │
```

---

## Configuration Flow

Environment variables flow through layers:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Environment Variables                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ SPINE_DB_URL=postgresql://user:pass@localhost:5432/spine                    │
│ SPINE_FINRA_API_KEY=xxx                                                     │
│ SPINE_SLACK_WEBHOOK=https://hooks.slack.com/xxx                             │
│ SPINE_LOG_LEVEL=INFO                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                API Startup                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ # main.py                                                                   │
│ config = Settings()  # Loads from env                                       │
│ db = create_adapter(DatabaseConfig.from_env())                              │
│ alerter = AlertRouter()                                                     │
│ alerter.add_channel(SlackChannel(SlackConfig.from_env()))                   │
│ scheduler = SchedulerService(db)                                            │
│ runner = WorkflowRunner(registry)                                           │
│                                                                             │
│ app.state.db = db                                                           │
│ app.state.alerter = alerter                                                 │
│ app.state.scheduler = scheduler                                             │
│ app.state.runner = runner                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Dependency Injection                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ def get_db() -> DatabaseAdapter:                                            │
│     return app.state.db                                                     │
│                                                                             │
│ def get_runner() -> WorkflowRunner:                                         │
│     return app.state.runner                                                 │
│                                                                             │
│ @router.post("/run")                                                        │
│ async def run(runner: WorkflowRunner = Depends(get_runner)):                │
│     ...                                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Error Flow

Errors propagate up with context:

```
┌────────────────┐
│ Source Error   │  ─────►  TransientError("FINRA API timeout")
└────────────────┘                     │
                                       ▼
┌────────────────┐          ┌──────────────────────┐
│ Pipeline Step  │  ─────►  │ error.with_context(  │
└────────────────┘          │   step="fetch",      │
                            │   pipeline="ingest", │
                            │   execution_id="abc" │
                            │ )                    │
                            └──────────────────────┘
                                       │
                                       ▼
┌────────────────┐          ┌──────────────────────┐
│ Orchestration  │  ─────►  │ Record to history    │
└────────────────┘          │ Send alert           │
                            │ Return error result  │
                            └──────────────────────┘
                                       │
                                       ▼
┌────────────────┐          ┌──────────────────────┐
│ API Response   │  ─────►  │ {                    │
└────────────────┘          │   "status": "FAILED",│
                            │   "error": "...",    │
                            │   "category": "..."  │
                            │ }                    │
                            └──────────────────────┘
                                       │
                                       ▼
┌────────────────┐          ┌──────────────────────┐
│ Frontend       │  ─────►  │ Show error toast     │
└────────────────┘          │ Display in UI        │
                            │ Offer retry option   │
                            └──────────────────────┘
```

---

## Next Steps

1. View FINRA example: [10-FINRA-EXAMPLE.md](./10-FINRA-EXAMPLE.md)
2. Review implementation order: [11-IMPLEMENTATION-ORDER.md](./11-IMPLEMENTATION-ORDER.md)
