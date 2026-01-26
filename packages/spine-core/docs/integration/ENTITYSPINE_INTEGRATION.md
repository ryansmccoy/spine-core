# EntitySpine Integration Guide

## Overview

EntitySpine uses **ad-hoc execution methods** (FastAPI BackgroundTasks, asyncio tasks, CLI scripts) with no Celery or distributed queue. The existing `RefreshResult` and `SyncResult` dataclasses provide good models for unified tracking.

---

## Current Execution Patterns

| Pattern | Location | Description |
|---------|----------|-------------|
| **Scheduler** | `api/scheduler.py` | `DataRefreshScheduler` - background refresh loop |
| **Background Tasks** | `api/main.py` | FastAPI `BackgroundTasks` for on-demand refresh |
| **CLI** | `src/entityspine/cli.py` | Direct async execution for resolve/search/load |
| **Scripts** | `scripts/` | One-shot data loading pipelines |
| **Services** | `services/` | `RefreshService`, `SyncService` with result tracking |

---

## Integration Opportunities

### 1. Data Refresh → WorkSpec

**Current:** Direct call in `api/scheduler.py`
```python
async def refresh_sec_data(self):
    result = await self.refresh_service.refresh_from_sec()
```

**Unified:**
```python
from spine.execution import Dispatcher, task_spec

run_id = await dispatcher.submit_task("entityspine.refresh_sec", {
    "force": False,
    "incremental": True,
})
```

### 2. Multi-Source Load → Pipeline

**Current:** Script `scripts/full_multi_source_load.py`
```python
await load_from_thomson()
await load_from_bloomberg()
await load_from_factset()
```

**Unified:**
```python
run_id = await dispatcher.submit_pipeline("entityspine.multi_source_load", {
    "sources": ["thomson", "bloomberg", "factset"],
})
```

### 3. Sync Operations → WorkSpec

**Current:** `services/sync_service.py`
```python
async def full_sync(self) -> SyncResult:
    # Sync PostgreSQL → ES/Neo4j
```

**Unified:**
```python
run_id = await dispatcher.submit_task("entityspine.sync", {
    "mode": "full",  # or "incremental"
    "targets": ["elasticsearch", "neo4j"],
})
```

### 4. Batch Resolution → Workflow

**Current:** CLI `entityspine batch <queries>`

**Unified:**
```python
run_id = await dispatcher.submit_workflow("entityspine.batch_resolve", {
    "queries": ["AAPL", "MSFT", "GOOGL"],
    "parallel": True,
})
```

### 5. API Endpoints → Dispatcher

**Current:** `api/main.py`
```python
@app.post("/refresh/sec")
async def trigger_refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(refresh_sec_data)
```

**Unified:**
```python
@app.post("/refresh/sec")
async def trigger_refresh(dispatcher: Dispatcher):
    run_id = await dispatcher.submit_task("entityspine.refresh_sec", {})
    return {"run_id": run_id}
```

---

## Handler Registration

```python
from spine.execution import HandlerRegistry
from spine.execution.executors import MemoryExecutor

# Define handlers
async def refresh_sec_handler(params: dict) -> dict:
    force = params.get("force", False)
    result = await refresh_service.refresh_from_sec(force=force)
    return {"loaded": result.loaded_count, "updated": result.updated_count}

async def refresh_gleif_handler(params: dict) -> dict:
    result = await refresh_service.refresh_from_gleif()
    return {"loaded": result.loaded_count}

async def sync_handler(params: dict) -> dict:
    mode = params.get("mode", "incremental")
    result = await sync_service.sync(mode=mode)
    return {"synced": result.synced_count}

async def batch_resolve_handler(params: dict) -> dict:
    queries = params["queries"]
    results = await resolver.batch_resolve(queries)
    return {"resolved": len(results), "results": results}

async def multi_source_load_handler(params: dict) -> dict:
    sources = params.get("sources", ["sec", "gleif"])
    totals = {}
    for source in sources:
        result = await load_from_source(source)
        totals[source] = result.count
    return {"loaded": totals}

# Register
handlers = {
    "task:refresh_sec": refresh_sec_handler,
    "task:refresh_gleif": refresh_gleif_handler,
    "task:sync": sync_handler,
    "task:batch_resolve": batch_resolve_handler,
    "pipeline:multi_source_load": multi_source_load_handler,
}

executor = MemoryExecutor(handlers=handlers)
dispatcher = Dispatcher(executor=executor)
```

---

## WorkSpec Types for EntitySpine

| Kind | Name | Purpose |
|------|------|---------|
| `task` | `refresh_sec` | Refresh SEC company data |
| `task` | `refresh_gleif` | Refresh GLEIF LEI data |
| `task` | `refresh_all` | Refresh all sources |
| `task` | `sync` | Sync PostgreSQL → ES/Neo4j |
| `task` | `batch_resolve` | Resolve multiple identifiers |
| `pipeline` | `multi_source_load` | Load Thomson + Bloomberg + FactSet |
| `workflow` | `daily_refresh` | Scheduled daily data refresh |

---

## Key Files to Modify

| File | Change |
|------|--------|
| `api/scheduler.py` | Replace direct calls with `dispatcher.submit_task()` |
| `api/main.py` | Replace `BackgroundTasks` with Dispatcher |
| `src/entityspine/cli.py` | Route commands through Dispatcher |
| `services/refresh_service.py` | Wrap as handler functions |
| `services/sync_service.py` | Wrap as handler functions |
| `scripts/*.py` | Convert to pipeline specs |

---

## Scheduler Migration

**Current:** `DataRefreshScheduler` with `asyncio.create_task()`
```python
class DataRefreshScheduler:
    async def _refresh_loop(self):
        while True:
            await asyncio.sleep(self.check_interval)
            if self._should_refresh_sec():
                await self.refresh_sec_data()
```

**Unified:** Use Celery Beat or APScheduler with Dispatcher
```python
# Celery Beat Schedule
beat_schedule = {
    "refresh-sec-daily": {
        "task": "entityspine.tasks.dispatch_refresh",
        "schedule": crontab(hour=6, minute=0),
        "args": ("refresh_sec", {}),
    },
    "refresh-gleif-weekly": {
        "task": "entityspine.tasks.dispatch_refresh",
        "schedule": crontab(hour=6, minute=0, day_of_week=0),
        "args": ("refresh_gleif", {}),
    },
}

@celery_app.task
def dispatch_refresh(task_name: str, params: dict):
    return asyncio.run(dispatcher.submit_task(task_name, params))
```

---

## Result Tracking Alignment

**Current:** `RefreshResult` in services
```python
@dataclass
class RefreshResult:
    source: str
    loaded_count: int
    updated_count: int
    error_count: int
    duration_seconds: float
```

**Unified:** Map to `RunRecord.result`
```python
run = await dispatcher.get_run(run_id)
# run.result = {"source": "sec", "loaded_count": 1000, ...}
# run.duration_seconds = 45.2
# run.status = RunStatus.COMPLETED
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                  EntitySpine + spine-core                       │
│                                                                 │
│  ┌──────────┐    ┌────────────┐    ┌──────────────────────────┐│
│  │ API/CLI  │───▶│ Dispatcher │───▶│ Executor                 ││
│  │ Scheduler│    └────────────┘    │  • MemoryExecutor (dev)  ││
│  └──────────┘          │           │  • CeleryExecutor (prod) ││
│                        ▼           └──────────────────────────┘│
│                 ┌────────────┐                │                 │
│                 │ RunRecord  │◄───────────────┘                 │
│                 └────────────┘                                  │
│                        │                                        │
│                        ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │               EntitySpine Handlers                        │  │
│  │  refresh_sec │ refresh_gleif │ sync │ batch_resolve      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                        │                                        │
│                        ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Data Stores                             │  │
│  │       PostgreSQL  │  Elasticsearch  │  Neo4j              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Benefits

1. **Consistent Tracking:** All refresh/sync operations tracked uniformly
2. **Idempotency:** Prevent duplicate refreshes with idempotency keys
3. **Progress Reporting:** Long-running syncs report progress via events
4. **Retry Logic:** Built-in retry for transient failures
5. **Observability:** Full audit trail of all data operations
