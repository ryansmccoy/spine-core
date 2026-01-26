# Spine-Core Migration Tracker

## Overview

This document tracks **every identified integration point** across all spine applications, with status tracking to ensure complete migration.

---

## Legend

| Status | Meaning |
|--------|---------|
| ⬜ | Not Started |
| 🟡 | In Progress |
| ✅ | Completed |
| ➖ | N/A (already unified or not applicable) |

---

## FeedSpine

### Source Files Analyzed
- `feedspine/src/feedspine/pipeline.py`
- `feedspine/src/feedspine/scheduler/memory.py`
- `feedspine/src/feedspine/executor/sync.py`
- `feedspine/src/feedspine/queue/memory.py`
- `feedspine/src/feedspine/core/feedspine.py`
- `feedspine/src/feedspine/cli.py`
- `feedspine/src/feedspine/api/routes/feeds.py`
- `feedspine/src/feedspine/models/task.py`
- `feedspine/src/feedspine/models/run_event.py`
- `feedspine/src/feedspine/models/feed_run.py`
- `feedspine/src/feedspine/protocols/executor.py`
- `feedspine/src/feedspine/protocols/scheduler.py`

### Migration Items

| ID | File | Current Pattern | Target Pattern | Status |
|----|------|-----------------|----------------|--------|
| FS-001 | `pipeline.py#L337` | `Pipeline.run()` direct execution | `dispatcher.submit_pipeline()` | ⬜ |
| FS-002 | `core/feedspine.py#L201` | `FeedSpine.collect()` | Route through Dispatcher | ⬜ |
| FS-003 | `scheduler/memory.py` | `MemoryScheduler` (loses state) | Add `SQLScheduler` or `RedisScheduler` | ⬜ |
| FS-004 | `executor/sync.py` | `SyncExecutor` only | Add `CeleryExecutor` option | ⬜ |
| FS-005 | `cli.py#L203-299` | `ingest` command direct execution | `dispatcher.submit_task()` | ⬜ |
| FS-006 | `cli.py#L373-448` | `sync` command direct execution | `dispatcher.submit_task()` | ⬜ |
| FS-007 | `api/routes/feeds.py` | Direct feed collection trigger | Route through Dispatcher | ⬜ |
| FS-008 | `models/task.py` | Custom `Task` model | Map to `WorkSpec` | ⬜ |
| FS-009 | `models/feed_run.py` | Custom `FeedRun` | Store in `RunRecord.result` | ⬜ |

---

## EntitySpine

### Source Files Analyzed
- `entityspine/src/entityspine/api/scheduler.py`
- `entityspine/src/entityspine/api/main.py`
- `entityspine/src/entityspine/cli.py`
- `entityspine/src/entityspine/services/refresh_service.py`
- `entityspine/src/entityspine/services/sync_service.py`
- `entityspine/scripts/full_multi_source_load.py`
- `entityspine/scripts/load_all_reference_data.py`

### Migration Items

| ID | File | Current Pattern | Target Pattern | Status |
|----|------|-----------------|----------------|--------|
| ES-001 | `api/scheduler.py` | `DataRefreshScheduler._refresh_loop()` | Celery Beat + Dispatcher | ⬜ |
| ES-002 | `api/scheduler.py` | `asyncio.create_task()` for background | `dispatcher.submit_task()` | ⬜ |
| ES-003 | `api/main.py` | `BackgroundTasks.add_task(refresh_sec)` | `dispatcher.submit_task()` | ⬜ |
| ES-004 | `api/main.py` | `BackgroundTasks.add_task(refresh_all)` | `dispatcher.submit_task()` | ⬜ |
| ES-005 | `cli.py` | `resolve` direct execution | `dispatcher.submit_task()` | ⬜ |
| ES-006 | `cli.py` | `batch` direct execution | `dispatcher.submit_workflow()` | ⬜ |
| ES-007 | `cli.py` | `db load-sec` direct execution | `dispatcher.submit_task()` | ⬜ |
| ES-008 | `services/refresh_service.py` | `RefreshResult` dataclass | Store in `RunRecord.result` | ⬜ |
| ES-009 | `services/sync_service.py` | `SyncResult` dataclass | Store in `RunRecord.result` | ⬜ |
| ES-010 | `scripts/full_multi_source_load.py` | Script with direct calls | `dispatcher.submit_pipeline()` | ⬜ |
| ES-011 | `scripts/load_all_reference_data.py` | Script with direct calls | `dispatcher.submit_pipeline()` | ⬜ |

---

## GenAI-Spine

### Source Files Analyzed
- `genai-spine/src/genai_spine/__main__.py`
- `genai-spine/src/genai_spine/cli.py`
- `genai-spine/src/genai_spine/api/routers/capabilities.py`
- `genai-spine/src/genai_spine/api/routers/completions.py`
- `genai-spine/src/genai_spine/capabilities/summarize.py`
- `genai-spine/src/genai_spine/capabilities/extract.py`
- `genai-spine/src/genai_spine/services/tracking.py`

### Migration Items

| ID | File | Current Pattern | Target Pattern | Status |
|----|------|-----------------|----------------|--------|
| GS-001 | `api/routers/capabilities.py` | Sync-only `/summarize` | Add async dispatch option | ⬜ |
| GS-002 | `api/routers/capabilities.py` | Sync-only `/extract` | Add async dispatch option | ⬜ |
| GS-003 | `api/routers/capabilities.py` | Sync-only `/classify` | Add async dispatch option | ⬜ |
| GS-004 | `api/routers/capabilities.py` | Sync-only `/rewrite` | Add async dispatch option | ⬜ |
| GS-005 | `api/routers/completions.py` | Sync-only `/chat/completions` | Add async dispatch option | ⬜ |
| GS-006 | N/A | No batch endpoint | Add `dispatcher.submit_workflow("batch_*")` | ⬜ |
| GS-007 | N/A | No GPU lane routing | Add `lane="gpu"` for embeddings | ⬜ |
| GS-008 | `services/tracking.py` | On-demand cost aggregation | Scheduled task via Dispatcher | ⬜ |
| GS-009 | N/A | No Celery infrastructure | Add Celery app + workers | ⬜ |

---

## Document-Spine

### Source Files Analyzed
- `document-spine/src/document_spine/cli/__init__.py`
- `document-spine/src/document_spine/models/ingestion.py`
- `document-spine/src/document_spine/integrations/spine_core.py`
- `document-spine/src/document_spine/integrations/capture_spine.py`
- `document-spine/src/document_spine/ingestion/scanner.py`
- `document-spine/src/document_spine/ingestion/chunker.py`
- `document-spine/src/document_spine/projections/sqlite_fts.py`

### Migration Items

| ID | File | Current Pattern | Target Pattern | Status |
|----|------|-----------------|----------------|--------|
| DS-001 | `cli/__init__.py` | `scan` command direct execution | `dispatcher.submit_pipeline()` | ⬜ |
| DS-002 | `cli/__init__.py` | `search` command direct execution | `dispatcher.submit_task()` | ⬜ |
| DS-003 | `cli/__init__.py` | `rebuild` command direct execution | `dispatcher.submit_pipeline()` | ⬜ |
| DS-004 | `models/ingestion.py` | `IngestionRun` custom model | Map to `RunRecord` | ⬜ |
| DS-005 | `integrations/spine_core.py` | `Pipeline` base class (NOT WIRED) | Wire to Dispatcher | ⬜ |
| DS-006 | `integrations/capture_spine.py` | `@register_parser` decorator | Register as task handlers | ⬜ |
| DS-007 | `ingestion/scanner.py` | `DirectoryScanner.scan()` | Wrap in `scan` handler | ⬜ |
| DS-008 | `ingestion/chunker.py` | Direct chunking | Wrap in `chunk` handler | ⬜ |
| DS-009 | `projections/sqlite_fts.py` | Direct indexing | Wrap in `index` handler | ⬜ |
| DS-010 | N/A | No REST API | Add FastAPI routes + `/runs` | ⬜ |

---

## Capture-Spine

### Source Files Analyzed
- `capture-spine/app/orchestration/dispatcher.py`
- `capture-spine/app/orchestration/models.py`
- `capture-spine/app/orchestration/celery_backend.py`
- `capture-spine/app/tasks/run_pipeline.py`
- `capture-spine/app/tasks/scheduler.py`
- `capture-spine/app/tasks/batch_ingestion_tasks.py`
- `capture-spine/app/tasks/copilot_chat_sync.py`
- `capture-spine/app/tasks/backup.py`
- `capture-spine/app/tasks/sync.py`
- `capture-spine/app/tasks/recommendations.py`
- `capture-spine/app/runtime/runner.py`
- `capture-spine/app/features/jobs/service.py`
- `capture-spine/app/features/tasks/service.py`
- `capture-spine/app/pipelines/`

### Migration Items

| ID | File | Current Pattern | Target Pattern | Status |
|----|------|-----------------|----------------|--------|
| CS-001 | `orchestration/dispatcher.py` | Custom `Dispatcher` | ➖ Already unified (align schema) | ➖ |
| CS-002 | `orchestration/models.py` | `Execution` dataclass | Map to spine-core `RunRecord` | ⬜ |
| CS-003 | `tasks/run_pipeline.py` | `run_pipeline` Celery task | ➖ Already unified | ➖ |
| CS-004 | `tasks/scheduler.py` | Beat tasks via dispatcher | ➖ Already unified | ➖ |
| CS-005 | `tasks/batch_ingestion_tasks.py` | **BYPASS** - direct Celery | Route through Dispatcher | ⬜ |
| CS-006 | `tasks/copilot_chat_sync.py` | **BYPASS** - direct Celery | Route through Dispatcher | ⬜ |
| CS-007 | `tasks/backup.py` | **BYPASS** - 4 direct tasks | Route through Dispatcher | ⬜ |
| CS-008 | `tasks/sync.py` | **BYPASS** - direct Celery | Route through Dispatcher | ⬜ |
| CS-009 | `tasks/recommendations.py` | **BYPASS** - direct Celery | Route through Dispatcher | ⬜ |
| CS-010 | `features/jobs/service.py` | Legacy `jobs` table | Consolidate to `executions` | ⬜ |

---

## Market-Spine

### Source Files Analyzed
- `market-spine/src/market_spine/orchestrator/dispatcher.py`
- `market-spine/src/market_spine/orchestrator/backends/`
- `market-spine/src/market_spine/celery.py`
- `market-spine/src/market_spine/jobs/schedule.py`
- `market-spine/src/market_spine/jobs/ingest.py`
- `market-spine/src/market_spine/jobs/calcs.py`
- `market-spine/src/market_spine/calcs/registry.py`
- `market-spine/src/market_spine/calcs/engine.py`
- `market-spine/src/market_spine/pipelines/runner.py`
- `market-spine/src/market_spine/services/execution.py`

### Migration Items

| ID | File | Current Pattern | Target Pattern | Status |
|----|------|-----------------|----------------|--------|
| MS-001 | `orchestrator/dispatcher.py` | Custom `dispatch()` | ➖ Reference implementation | ➖ |
| MS-002 | `orchestrator/backends/` | Multi-backend support | ➖ Reference implementation | ➖ |
| MS-003 | `jobs/ingest.py` | Deprecation shims | Complete removal (2026-Q2) | ⬜ |
| MS-004 | `jobs/calcs.py` | Dispatch wrappers | ➖ Already routes to dispatch | ➖ |
| MS-005 | `orchestrator/` vs `orchestrators/` | Dual modules | Consolidate to single module | ⬜ |
| MS-006 | Schema alignment | Custom `ExecutionParams` | Align with spine-core `WorkSpec` | ⬜ |

---

## Summary Statistics

| Application | Total Items | Not Started | In Progress | Completed | N/A |
|-------------|-------------|-------------|-------------|-----------|-----|
| FeedSpine | 9 | 9 | 0 | 0 | 0 |
| EntitySpine | 11 | 11 | 0 | 0 | 0 |
| GenAI-Spine | 9 | 9 | 0 | 0 | 0 |
| Document-Spine | 10 | 10 | 0 | 0 | 0 |
| Capture-Spine | 10 | 6 | 0 | 0 | 4 |
| Market-Spine | 6 | 3 | 0 | 0 | 3 |
| **TOTAL** | **55** | **48** | **0** | **0** | **7** |

---

## How to Use This Tracker

### When Starting Work
1. Find the item by ID (e.g., `FS-001`)
2. Update status to 🟡
3. Note the PR/commit in comments

### When Completing Work
1. Update status to ✅
2. Add link to PR that implemented it
3. Update summary statistics

### Validation Checklist

For each migrated item, verify:
- [ ] Handler registered in `handlers` dict
- [ ] Entry point routes through Dispatcher
- [ ] `RunRecord` created and persisted
- [ ] Events emitted for lifecycle
- [ ] Tests pass
- [ ] Old code path removed or deprecated

---

## Priority Order

### Phase 1: Capture-Spine Bypasses (High Value, Low Effort)
Already has Dispatcher - just route bypass tasks through it.
- CS-005, CS-006, CS-007, CS-008, CS-009

### Phase 2: FeedSpine (Medium Effort)
Protocol-based architecture ready for integration.
- FS-001, FS-002, FS-007

### Phase 3: EntitySpine (Medium Effort)
Replace BackgroundTasks with Dispatcher.
- ES-001, ES-002, ES-003, ES-004

### Phase 4: Document-Spine (Medium Effort)
Wire existing spine_core integration.
- DS-005, DS-001, DS-003

### Phase 5: GenAI-Spine (High Effort)
Add async infrastructure from scratch.
- GS-009 first (Celery setup), then others

### Phase 6: Cleanup
- MS-003 (remove deprecated shims)
- MS-005 (consolidate modules)
- CS-010 (consolidate job tables)
