# FeedSpine Integration Guide

## Overview

FeedSpine has a **protocol-based architecture** with existing patterns for Pipeline, Scheduler, Executor, and Queue that align well with spine-core's unified execution model.

---

## Current Execution Patterns

| Pattern | Location | Description |
|---------|----------|-------------|
| **Pipeline** | `pipeline.py#L136-431` | `Pipeline.run()` orchestrates feed processing |
| **Scheduler** | `scheduler/memory.py` | `MemoryScheduler` - in-memory feed scheduling |
| **Executor** | `executor/sync.py` | `SyncExecutor` - synchronous task execution |
| **Queue** | `queue/memory.py` | `MemoryQueue` - pub/sub messaging |
| **FeedSpine** | `core/feedspine.py#L74-250` | Main orchestrator with `collect()` method |

---

## Integration Opportunities

### 1. Task Model → WorkSpec

**Current:** `Task` model in `models/task.py`
```python
@dataclass
class Task:
    callable: Callable
    args: tuple
    kwargs: dict
    retries: int
    timeout: float
    priority: int
```

**Unified:** Map to `WorkSpec`
```python
from spine.execution import task_spec

spec = task_spec("feedspine.fetch_otc", {
    "tier": "NMS_TIER_1",
    "date": "2026-01-15",
}, priority="high", lane="feeds")
```

### 2. Pipeline.run() → Dispatcher

**Current:** Direct execution in `pipeline.py#L337`
```python
async def run(self, feed: Feed) -> PipelineResult:
    # Direct processing
```

**Unified:** Route through Dispatcher
```python
from spine.execution import Dispatcher

run_id = await dispatcher.submit_pipeline("feedspine.ingest", {
    "feed_id": feed.id,
    "tier": feed.tier,
})
```

### 3. Scheduler → Persistent Scheduler

**Current:** `MemoryScheduler` loses state on restart

**Unified:** Add `SQLScheduler` or `RedisScheduler` implementations

### 4. CLI Commands → Dispatcher

**Current:** Direct `asyncio.run()` in CLI

**Unified:**
```python
@cli.command()
async def collect(feed_name: str):
    run_id = await dispatcher.submit_task("feedspine.collect", {
        "feed_name": feed_name
    })
    # Poll for completion
```

### 5. API Triggers → Dispatcher

**Current:** `api/routes/feeds.py` triggers collection directly

**Unified:**
```python
@router.post("/feeds/{feed_id}/collect")
async def trigger_collection(feed_id: str, dispatcher: Dispatcher):
    return await dispatcher.submit_pipeline("feedspine.ingest", {
        "feed_id": feed_id
    })
```

---

## Handler Registration

```python
from spine.execution import HandlerRegistry
from spine.execution.executors import MemoryExecutor, CeleryExecutor

# Define handlers
async def fetch_otc_quotes(params: dict) -> dict:
    tier = params.get("tier", "NMS_TIER_1")
    # ... fetch logic
    return {"quotes": quotes, "count": len(quotes)}

async def validate_quotes(params: dict) -> dict:
    # ... validation logic
    return {"valid": valid_count, "invalid": invalid_count}

async def run_feed_pipeline(params: dict) -> dict:
    # ... orchestrate fetch + validate
    return {"fetched": 100, "valid": 98}

# Register
handlers = {
    "task:fetch_otc_quotes": fetch_otc_quotes,
    "task:validate_quotes": validate_quotes,
    "pipeline:feed_ingestion": run_feed_pipeline,
}

# Create executor (swap for production)
executor = MemoryExecutor(handlers=handlers)  # Dev
# executor = CeleryExecutor(app=celery_app)   # Prod
```

---

## WorkSpec Types for FeedSpine

| Kind | Name | Purpose |
|------|------|---------|
| `task` | `fetch_otc_quotes` | Fetch quotes from FINRA |
| `task` | `validate_quotes` | Validate quote data |
| `task` | `store_quotes` | Persist to storage |
| `task` | `notify_subscribers` | Pub/sub notifications |
| `pipeline` | `feed_ingestion` | Full fetch → validate → store → notify |
| `workflow` | `daily_feed_run` | All feeds for a day |

---

## Key Files to Modify

| File | Change |
|------|--------|
| `protocols/executor.py` | Add `WorkSpec` as alternate task definition |
| `core/feedspine.py#L201` | `collect()` routes through Dispatcher |
| `pipeline.py#L337` | `run()` wraps work in WorkSpec |
| `scheduler/` | Add `SQLScheduler` implementation |
| `api/routes/feeds.py` | Route triggers through Dispatcher |
| `cli.py` | Replace direct execution with dispatch |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    FeedSpine + spine-core                       │
│                                                                 │
│  ┌──────────┐    ┌────────────┐    ┌──────────────────────────┐│
│  │ CLI/API  │───▶│ Dispatcher │───▶│ Executor (swap backends) ││
│  └──────────┘    └────────────┘    │  • MemoryExecutor (dev)  ││
│                        │           │  • CeleryExecutor (prod) ││
│                        ▼           └──────────────────────────┘│
│                 ┌────────────┐                │                 │
│                 │ RunRecord  │◄───────────────┘                 │
│                 │ (tracking) │                                  │
│                 └────────────┘                                  │
│                        │                                        │
│                        ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                 FeedSpine Handlers                        │  │
│  │  fetch_otc_quotes │ validate_quotes │ run_feed_pipeline  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Benefits

1. **Executor Swapping:** MemoryExecutor for tests, CeleryExecutor for production
2. **Unified Tracking:** All feed runs tracked via RunRecord
3. **Idempotency:** Prevent duplicate feed processing
4. **Observability:** Events for all lifecycle stages
5. **Priority Routing:** High-priority feeds get faster processing
