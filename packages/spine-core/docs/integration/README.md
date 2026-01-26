# Spine-Core Integration Overview

## Introduction

This directory contains integration guides for applying the **Unified Execution Contract** from `spine-core` to each spine application in the ecosystem.

---

## Integration Maturity Matrix

| Application | Current State | Integration Effort | Priority |
|-------------|---------------|-------------------|----------|
| **Market-Spine** | ✅ Reference Implementation | Low (already done) | N/A |
| **Capture-Spine** | ✅ Mostly Unified | Low (unify bypass tasks) | High |
| **FeedSpine** | ⚠️ Protocol-Based | Medium (wire protocols) | High |
| **EntitySpine** | ⚠️ Ad-Hoc Execution | Medium (replace BackgroundTasks) | Medium |
| **Document-Spine** | ⚠️ CLI-Only | Medium (add API + Dispatcher) | Medium |
| **GenAI-Spine** | ❌ No Background Jobs | High (add async infrastructure) | Low |

---

## Integration Guides by Application

### [Market-Spine](MARKET_SPINE_INTEGRATION.md) ⭐ Reference
- **Status:** Already implements unified pattern
- **Use As:** Template for other integrations
- **Key Pattern:** Multi-backend support (Celery, Dagster, Prefect, etc.)

### [Capture-Spine](CAPTURE_SPINE_INTEGRATION.md)
- **Status:** Dispatcher exists, some tasks bypass it
- **Action:** Route `batch_import`, `copilot_sync`, `backup`, `recommendations` through Dispatcher
- **Benefit:** Single tracking table, consistent events

### [FeedSpine](FEEDSPINE_INTEGRATION.md)
- **Status:** Protocol-based architecture ready for integration
- **Action:** Wire `Pipeline`, `Scheduler`, `Executor` protocols to spine-core
- **Benefit:** Swap MemoryExecutor for CeleryExecutor in production

### [EntitySpine](ENTITYSPINE_INTEGRATION.md)
- **Status:** Uses FastAPI BackgroundTasks, asyncio.create_task()
- **Action:** Replace with Dispatcher, add persistent scheduler
- **Benefit:** Unified refresh/sync tracking, retry logic

### [Document-Spine](DOCUMENT_SPINE_INTEGRATION.md)
- **Status:** CLI-only with `IngestionRun` model
- **Action:** Wire existing spine_core integration, add API
- **Benefit:** REST API for document processing, progress tracking

### [GenAI-Spine](GENAI_SPINE_INTEGRATION.md)
- **Status:** Synchronous request-response only
- **Action:** Add batch endpoints, async dispatch, GPU routing
- **Benefit:** Process large batches without timeout, cost tracking per run

---

## Quick Reference: Common Patterns

### Handler Registration
```python
from spine.execution import Dispatcher
from spine.execution.executors import MemoryExecutor

handlers = {
    "task:my_task": my_task_handler,
    "pipeline:my_pipeline": my_pipeline_handler,
}

executor = MemoryExecutor(handlers=handlers)
dispatcher = Dispatcher(executor=executor)
```

### Submit Work
```python
# Task
run_id = await dispatcher.submit_task("my_task", {"param": "value"})

# Pipeline
run_id = await dispatcher.submit_pipeline("my_pipeline", {"date": "2026-01-15"})

# Workflow
run_id = await dispatcher.submit_workflow("my_workflow", {"items": [...]})
```

### Query Results
```python
run = await dispatcher.get_run(run_id)
print(run.status)  # RunStatus.COMPLETED
print(run.result)  # Handler output
```

### Priority Routing
```python
# High-priority user-facing
await dispatcher.submit_task("search", params, priority="realtime")

# GPU lane
await dispatcher.submit_task("embed", params, lane="gpu")

# Low-priority batch
await dispatcher.submit_pipeline("batch", params, priority="low")
```

---

## Integration Steps (General)

### Step 1: Identify Current Execution Patterns
- CLI commands
- API endpoints that trigger work
- Celery tasks
- Scheduled jobs
- Background tasks

### Step 2: Define Handlers
```python
# handlers.py
async def my_handler(params: dict) -> dict:
    # Your business logic
    return {"result": "value"}
```

### Step 3: Register Handlers
```python
handlers = {"task:my_handler": my_handler}
executor = MemoryExecutor(handlers=handlers)
dispatcher = Dispatcher(executor=executor)
```

### Step 4: Route Entry Points to Dispatcher
```python
# CLI
@cli.command()
async def my_command(ctx, ...):
    run_id = await ctx.obj["dispatcher"].submit_task("my_handler", {...})

# API
@router.post("/my-endpoint")
async def my_endpoint(dispatcher: Dispatcher):
    run_id = await dispatcher.submit_task("my_handler", {...})
    return {"run_id": run_id}

# Celery Beat
@celery_app.task
def scheduled_dispatch():
    asyncio.run(dispatcher.submit_task("my_handler", {...}))
```

### Step 5: Swap Executor for Production
```python
# Development
executor = MemoryExecutor(handlers=handlers)

# Production
executor = CeleryExecutor(app=celery_app)
```

---

## Benefits Summary

| Benefit | Description |
|---------|-------------|
| **Unified API** | Same `submit()` for tasks, pipelines, workflows |
| **Runtime Agnostic** | Swap executors without changing business logic |
| **Consistent Tracking** | Single `RunRecord` model for all work |
| **Observability** | Events for all lifecycle stages |
| **Idempotency** | Prevent duplicate processing |
| **Priority Routing** | Lane-based queue routing |
| **Cross-Spine Orchestration** | Workflows can call any spine's handlers |

---

## File Structure

```
docs/integration/
├── README.md                      # This file
├── FEEDSPINE_INTEGRATION.md       # FeedSpine guide
├── ENTITYSPINE_INTEGRATION.md     # EntitySpine guide
├── GENAI_SPINE_INTEGRATION.md     # GenAI-Spine guide
├── DOCUMENT_SPINE_INTEGRATION.md  # Document-Spine guide
├── CAPTURE_SPINE_INTEGRATION.md   # Capture-Spine guide
└── MARKET_SPINE_INTEGRATION.md    # Market-Spine guide (reference)
```
