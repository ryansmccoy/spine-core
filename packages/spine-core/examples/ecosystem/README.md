# Spine-Core Ecosystem Examples

## Overview

These examples demonstrate how the **Unified Execution Contract** from `spine-core` enables standardized workflow execution across all spine applications:

| Example | Application | Description |
|---------|-------------|-------------|
| `01_feedspine_pipeline.py` | FeedSpine | Market data feed ingestion |
| `02_entityspine_workflow.py` | EntitySpine | SEC filing entity resolution |
| `03_genai_spine_tasks.py` | GenAI-Spine | Embedding generation and RAG |
| `04_document_spine_ingestion.py` | Document-Spine | Document parsing and search |
| `05_workflow_architecture.py` | Cross-Spine | Multi-app orchestration |

## Quick Start

### Run All Examples

```bash
cd spine-core/packages/spine-core
python examples/ecosystem/run_all.py
```

### Run Individual Examples

```bash
# FeedSpine - Market Data Feed Ingestion
python examples/ecosystem/01_feedspine_pipeline.py

# EntitySpine - SEC Filing Entity Resolution
python examples/ecosystem/02_entityspine_workflow.py

# GenAI-Spine - Embeddings and RAG
python examples/ecosystem/03_genai_spine_tasks.py

# Document-Spine - Document Parsing and Search
python examples/ecosystem/04_document_spine_ingestion.py

# Cross-Spine Workflow Orchestration
python examples/ecosystem/05_workflow_architecture.py
```

## Core Concepts Demonstrated

### 1. Unified Execution API

All spine apps use the **same** submission API:

```python
from spine.execution import Dispatcher, HandlerRegistry
from spine.execution.executors import MemoryExecutor

# 1. Register handlers
handlers = {"task:my_task": my_handler}
executor = MemoryExecutor(handlers=handlers)
dispatcher = Dispatcher(executor=executor)

# 2. Submit work (same API for all work types)
run_id = await dispatcher.submit_task("my_task", {"param": "value"})
run_id = await dispatcher.submit_pipeline("my_pipeline", {"date": "2026-01-15"})
run_id = await dispatcher.submit_workflow("my_workflow", {"tier": "NMS_TIER_1"})

# 3. Query results
run = await dispatcher.get_run(run_id)
print(run.status.value)  # "completed"
print(run.result)  # Handler output
```

### 2. WorkSpec - Universal Work Definition

```python
from spine.execution import WorkSpec, task_spec, pipeline_spec

# Full form
spec = WorkSpec(
    kind="task",           # task | pipeline | workflow | step
    name="send_email",     # Handler name
    params={"to": "user@example.com"},
    priority="high",       # realtime | high | normal | low | slow
    lane="default",        # Queue routing (gpu, cpu, io-bound)
    idempotency_key="email_123",  # Prevent duplicates
    correlation_id="batch_001",   # Link related runs
)

# Convenience shortcuts
spec = task_spec("send_email", {"to": "user@example.com"})
spec = pipeline_spec("ingest_otc", {"date": "2026-01-15"})
```

### 3. RunRecord - Execution State

```python
run = await dispatcher.get_run(run_id)

# Status tracking
run.status      # RunStatus.COMPLETED | PENDING | QUEUED | RUNNING | FAILED
run.created_at  # When created
run.started_at  # When execution began
run.completed_at # When finished

# Results
run.result      # Handler output on success
run.error       # Error message on failure

# Runtime tracking (key for runtime-agnostic design)
run.external_ref    # Runtime-specific ID (Celery task_id, K8s job name, etc.)
run.executor_name   # Which executor ran it (celery, local, memory, etc.)
```

### 4. Priority and Lane Routing

```python
# High-priority user-facing request
await dispatcher.submit_task("search", {"query": "revenue"}, 
    priority="realtime")

# GPU-accelerated embedding task
await dispatcher.submit_task("generate_embeddings", {"texts": texts},
    lane="gpu")

# Low-priority batch job
await dispatcher.submit_pipeline("batch_index", {"batch_id": "001"},
    priority="low", lane="batch")
```

### 5. Idempotency

```python
# First submission
run_id_1 = await dispatcher.submit_task("process", {"id": "123"},
    idempotency_key="process_123")

# Duplicate submission (returns same run_id!)
run_id_2 = await dispatcher.submit_task("process", {"id": "123"},
    idempotency_key="process_123")

assert run_id_1 == run_id_2  # True - no duplicate processing
```

### 6. Correlation IDs

```python
# All runs in a batch share a correlation_id
correlation = "batch_2026Q1"

for ticker in ["AAPL", "MSFT", "GOOGL"]:
    await dispatcher.submit_workflow("ingest", {"ticker": ticker},
        correlation_id=correlation)

# Query all runs in batch
runs = await dispatcher.list_runs()
batch_runs = [r for r in runs if r.correlation_id == correlation]
```

## Example Output

```
======================================================================
Spine-Core Ecosystem Examples Runner
======================================================================

============================================================
Running: FeedSpine - Market Data Feed Ingestion
============================================================
[1] Submitting task: fetch_otc_quotes
  Status: completed, Quotes: 3

[2] Submitting pipeline: feed_ingestion
  Status: completed, Stats: {'fetched': 2, 'valid': 2}

[OK] FeedSpine Example Complete!

============================================================
Running: Cross-Spine Workflow Orchestration
============================================================
[1] Cross-Spine Workflow: SEC Filing Ingestion
  Orchestrating: EntitySpine -> Document-Spine -> GenAI-Spine -> FeedSpine

  Status: completed
  Ticker: NVDA
  Pages: 85, Vectors: 500, Indexed: True
  Steps: 6

[2] Handler Discovery by Spine
  entityspine: 2 handlers
  document-spine: 2 handlers
  genai-spine: 1 handlers
  feedspine: 1 handlers

[OK] Workflow Architecture Example Complete!

======================================================================
SUMMARY
======================================================================
  [OK] 01_feedspine_pipeline.py
  [OK] 02_entityspine_workflow.py
  [OK] 03_genai_spine_tasks.py
  [OK] 04_document_spine_ingestion.py
  [OK] 05_workflow_architecture.py

Total: 5 | Passed: 5 | Failed: 0
```

## Architecture Benefits

1. **Single API**: All work types use `WorkSpec` + `Dispatcher`
2. **Runtime Agnostic**: Switch executors without changing business logic
3. **Cross-Spine Orchestration**: Workflows can call handlers from any spine
4. **Built-in Observability**: Correlation IDs, events, tags for filtering
5. **Idempotency**: Safe retries, no duplicate processing

## Files Structure

```
examples/ecosystem/
├── __init__.py
├── run_all.py                      # Runner script
├── 01_feedspine_pipeline.py        # FeedSpine example
├── 02_entityspine_workflow.py      # EntitySpine example
├── 03_genai_spine_tasks.py         # GenAI-Spine example
├── 04_document_spine_ingestion.py  # Document-Spine example
└── 05_workflow_architecture.py     # Cross-spine orchestration
```
