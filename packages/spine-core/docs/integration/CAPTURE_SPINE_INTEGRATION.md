# Capture-Spine Integration Guide

## Overview

Capture-Spine has **the most sophisticated orchestration system** with an existing Dispatcher pattern, Celery backend, and execution tracking. Some tasks bypass the dispatcher and should be unified.

---

## Current Architecture (Already Mature)

| Component | Location | Description |
|-----------|----------|-------------|
| **Dispatcher** | `app/orchestration/dispatcher.py` | Single entry point for pipeline execution |
| **Execution Model** | `app/orchestration/models.py` | `Execution`, `ExecutionStatus`, `Lane` |
| **Celery Backend** | `app/orchestration/celery_backend.py` | Production backend |
| **Runner** | `app/runtime/runner.py` | `run_execution()` core logic |
| **Pipelines** | `app/pipelines/` | Feed, Parse, Enrich, Capture, Search |

---

## Current Dispatcher Pattern

Already implemented:
```python
# app/orchestration/dispatcher.py
class Dispatcher:
    async def submit(
        self,
        pipeline: str,
        params: dict,
        lane: str = "normal",
        trigger_source: str = "api",
    ) -> Execution
    
    async def get_execution(self, execution_id: UUID) -> Execution
    async def list_executions(...) -> list[Execution]
```

---

## Tasks That BYPASS Dispatcher

These Celery tasks run directly without going through the orchestration layer:

| Task | Location | Issue |
|------|----------|-------|
| `batch_import_documents` | `app/tasks/batch_ingestion_tasks.py` | Direct Celery task |
| `sync_copilot_chats` | `app/tasks/copilot_chat_sync.py` | Direct Celery task |
| `schedule_pending_backups` | `app/tasks/backup.py` | Direct Celery task |
| `run_backup_for_user` | `app/tasks/backup.py` | Direct Celery task |
| `sync_environments` | `app/tasks/sync.py` | Direct Celery task |
| `update_recommendations` | `app/tasks/recommendations.py` | Direct Celery task |

---

## Integration Opportunities

### 1. Batch Ingestion → Dispatcher

**Current:** Direct Celery task
```python
@celery_app.task
def batch_import_documents(import_id: str, ...):
    # Direct execution
```

**Unified:**
```python
# Register as pipeline
async def batch_import_handler(params: dict) -> dict:
    import_id = params["import_id"]
    # ... existing logic
    return {"imported": count}

# Route through dispatcher
run_id = await dispatcher.submit("batch_import", {
    "import_id": import_id,
    "documents": doc_ids,
})
```

### 2. Copilot Chat Sync → Dispatcher

**Current:** Direct Celery task
```python
@celery_app.task
def sync_copilot_chats():
    # Direct execution
```

**Unified:**
```python
run_id = await dispatcher.submit("copilot_sync", {
    "workspace": workspace_path,
    "since": last_sync_time,
})
```

### 3. Backup Tasks → Dispatcher

**Current:** 4 separate Celery tasks

**Unified:**
```python
# Single backup pipeline with params
run_id = await dispatcher.submit("backup", {
    "user_id": user_id,
    "backup_type": "full",  # or "incremental"
})
```

### 4. Recommendations → Dispatcher

**Current:** Multiple ML tasks

**Unified:**
```python
run_id = await dispatcher.submit("recommendations", {
    "model": "collaborative",
    "user_id": user_id,
})
```

### 5. Legacy Jobs → Executions Only

**Current:** Dual systems (`jobs` table + `executions` table)

**Unified:** Consolidate to `executions` table only

---

## Handler Registration for New Pipelines

```python
# Add to app/pipelines/__init__.py

PIPELINE_HANDLERS = {
    # Existing (already unified)
    "feed_processing": FeedProcessingPipeline,
    "content_capture": ContentCapturePipeline,
    "backfill": BackfillPipeline,
    
    # NEW: Previously bypassed
    "batch_import": BatchImportPipeline,
    "copilot_sync": CopilotSyncPipeline,
    "backup": BackupPipeline,
    "recommendations": RecommendationsPipeline,
    "sync_environments": EnvironmentSyncPipeline,
}
```

---

## WorkSpec Alignment

**Current Capture-Spine:**
```python
@dataclass
class Execution:
    execution_id: UUID
    pipeline_name: str      # → WorkSpec.name
    params: dict            # → WorkSpec.params
    lane: str               # → WorkSpec.lane
    trigger_source: str     # → WorkSpec.trigger_source
    status: str             # → RunRecord.status
```

**spine-core:**
```python
@dataclass
class WorkSpec:
    kind: str               # task | pipeline | workflow
    name: str               # Pipeline name
    params: dict            # Parameters
    priority: str           # realtime | high | normal | low | slow
    lane: str               # Queue routing
    trigger_source: str     # api | schedule | webhook
```

**Mapping:**
| Capture-Spine | spine-core |
|---------------|------------|
| `Execution.pipeline_name` | `WorkSpec.name` |
| `Execution.params` | `WorkSpec.params` |
| `Execution.lane` | `WorkSpec.lane` (same values) |
| `Execution.trigger_source` | `WorkSpec.trigger_source` |
| `ExecutionStatus` | `RunStatus` (same states) |

---

## Migration Path

### Phase 1: Align Schemas
```python
# Map Execution → RunRecord
def to_run_record(execution: Execution) -> RunRecord:
    return RunRecord(
        run_id=str(execution.execution_id),
        spec=WorkSpec(
            kind="pipeline",
            name=execution.pipeline_name,
            params=execution.params,
            lane=execution.lane,
            trigger_source=execution.trigger_source,
        ),
        status=RunStatus(execution.status.value),
        created_at=execution.created_at,
        # ...
    )
```

### Phase 2: Route Bypass Tasks
```python
# Before
@celery_app.task
def batch_import_documents(...):
    # Direct execution

# After
@celery_app.task
def batch_import_documents(import_id: str, ...):
    # Route through dispatcher
    asyncio.run(dispatcher.submit("batch_import", {
        "import_id": import_id,
    }))
```

### Phase 3: Consolidate Job Tables
```sql
-- Migrate jobs → executions
INSERT INTO executions (...)
SELECT ... FROM jobs WHERE ...;

-- Eventually drop jobs table
```

---

## Key Files to Modify

| File | Change |
|------|--------|
| `app/tasks/batch_ingestion_tasks.py` | Route through dispatcher |
| `app/tasks/copilot_chat_sync.py` | Route through dispatcher |
| `app/tasks/backup.py` | Route through dispatcher |
| `app/tasks/sync.py` | Route through dispatcher |
| `app/tasks/recommendations.py` | Route through dispatcher |
| `app/features/jobs/service.py` | Deprecate in favor of executions |
| `app/pipelines/__init__.py` | Register new pipeline handlers |

---

## Architecture Diagram (Current vs Target)

### Current
```
                    ┌───────────────┐
                    │  Entry Points │
                    └───────┬───────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
    ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
    │Dispatcher│       │ Direct  │       │ Direct  │
    │ (unified)│       │ Celery  │       │ Celery  │
    └────┬────┘       │ Tasks   │       │ Tasks   │
         │            └─────────┘       └─────────┘
         ▼                │                  │
    ┌─────────┐           │                  │
    │Executions│◄─────────┘                  │
    │ Table   │                              │
    └─────────┘     (NO TRACKING)            │
                                             ▼
                                      ┌───────────┐
                                      │ Jobs Table│
                                      │ (legacy)  │
                                      └───────────┘
```

### Target
```
                    ┌───────────────┐
                    │  Entry Points │
                    │ API/CLI/Beat  │
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │   DISPATCHER  │
                    │ (ALL routes)  │
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │  Executions   │
                    │ (single table)│
                    └───────┬───────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
    ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
    │  Feed   │       │ Batch   │       │ Backup  │
    │ Pipeline│       │ Import  │       │ Pipeline│
    └─────────┘       └─────────┘       └─────────┘
```

---

## Benefits

1. **Unified Tracking:** All tasks tracked in `executions` table
2. **Consistent Events:** All tasks emit lifecycle events
3. **Single Query:** Query all work via `/api/v1/executions`
4. **Lane Routing:** All tasks respect priority lanes
5. **Observability:** Full audit trail for everything
6. **Simpler Debugging:** One place to look for any task
