# Document-Spine Integration Guide

## Overview

Document-Spine has **CLI-based synchronous execution** with an existing `IngestionRun` model that's very close to `RunRecord`. spine-core patterns exist in `integrations/spine_core.py` but are not wired up.

---

## Current Execution Patterns

| Pattern | Location | Description |
|---------|----------|-------------|
| **CLI Commands** | `cli/__init__.py` | `scan`, `search`, `rebuild` commands |
| **IngestionRun** | `models/ingestion.py` | Job tracking with status state machine |
| **Pipeline Base** | `integrations/spine_core.py` | `Pipeline` class (not wired) |
| **Parser Registry** | `integrations/capture_spine.py` | Pluggable document parsers |

---

## Existing IngestionRun Model

Already has job-like tracking:
```python
@dataclass
class IngestionRun:
    run_id: str
    project_id: str
    status: Literal["pending", "running", "completed", "failed"]
    scanned_count: int
    indexed_count: int
    error_count: int
    started_at: datetime
    completed_at: datetime | None
    checkpoint: dict  # For resumable processing
```

---

## Integration Opportunities

### 1. IngestionRun → WorkSpec + RunRecord

**Current:** Custom `IngestionRun` model
```python
run = IngestionRun(project_id="my-project", source_roots=["./src"])
run.start()
# ... execute ...
run.complete()
```

**Unified:**
```python
from spine.execution import Dispatcher, pipeline_spec

run_id = await dispatcher.submit_pipeline("document_spine.ingest", {
    "project_id": "my-project",
    "source_roots": ["./src"],
    "patterns": ["*.py", "*.md"],
    "chunk_size": 1000,
})

# IngestionRun becomes handler result stored in RunRecord.result
```

### 2. CLI scan → Dispatcher

**Current:** Direct execution in CLI
```python
@cli.command()
async def scan(path: str, chunk_size: int):
    run = IngestionRun(...)
    await scanner.scan_directory(path, run)
```

**Unified:**
```python
@cli.command()
async def scan(ctx, path: str, chunk_size: int):
    run_id = await ctx.obj["dispatcher"].submit_pipeline("document_spine.ingest", {
        "root_path": str(Path(path).resolve()),
        "chunk_size": chunk_size,
    })
    
    # Poll with progress
    while True:
        run = await dispatcher.get_run(run_id)
        if run.status.is_terminal:
            break
        click.echo(f"Progress: {run.result.get('progress_pct', 0):.1f}%")
        await asyncio.sleep(1)
```

### 3. Document Processing → Task Handlers

**Current:** Monolithic scan function

**Unified:** Split into composable handlers
```python
# Individual document processing
run_id = await dispatcher.submit_task("document_spine.parse", {
    "document_id": doc_id,
    "parser": "pdf",  # or "markdown", "code"
})

# Chunking
run_id = await dispatcher.submit_task("document_spine.chunk", {
    "revision_id": rev_id,
    "strategy": "semantic",
    "size": 1000,
})

# Indexing
run_id = await dispatcher.submit_task("document_spine.index", {
    "chunks": chunk_ids,
    "projection": "sqlite_fts",
})
```

### 4. Rebuild Command → Pipeline

**Current:** Direct rebuild call
```python
@cli.command()
async def rebuild():
    await projection.rebuild_from_canonical()
```

**Unified:**
```python
run_id = await dispatcher.submit_pipeline("document_spine.rebuild", {
    "projection": "sqlite_fts",
    "full": True,
})
```

### 5. Wire Existing spine_core Integration

**Current:** `integrations/spine_core.py` has `Pipeline` base class but not used

**Unified:** Connect to Dispatcher
```python
from document_spine.integrations.spine_core import Pipeline, PipelineStatus
from spine.execution import Dispatcher

# Register Pipeline as handler
async def pipeline_handler(params: dict) -> dict:
    pipeline = IngestionPipeline(params)
    result = await pipeline.run()
    return result.to_dict()

handlers = {"pipeline:ingest": pipeline_handler}
```

---

## Handler Registration

```python
from spine.execution import HandlerRegistry
from spine.execution.executors import MemoryExecutor

# Define handlers
async def scan_handler(params: dict) -> dict:
    root_path = params["root_path"]
    patterns = params.get("patterns", ["*.*"])
    
    scanner = DirectoryScanner(root_path, patterns)
    documents = await scanner.scan()
    
    return {
        "scanned": len(documents),
        "documents": [d.id for d in documents],
    }

async def parse_handler(params: dict) -> dict:
    document_id = params["document_id"]
    parser_name = params.get("parser", "auto")
    
    parser = get_parser(parser_name)
    result = await parser.parse(document_id)
    
    return {
        "revision_id": result.revision_id,
        "pages": result.page_count,
        "content_type": result.content_type,
    }

async def chunk_handler(params: dict) -> dict:
    revision_id = params["revision_id"]
    strategy = params.get("strategy", "fixed")
    size = params.get("size", 1000)
    
    chunker = get_chunker(strategy)
    chunks = await chunker.chunk(revision_id, size=size)
    
    return {
        "chunks": len(chunks),
        "chunk_ids": [c.id for c in chunks],
    }

async def index_handler(params: dict) -> dict:
    chunk_ids = params["chunk_ids"]
    projection = params.get("projection", "sqlite_fts")
    
    indexer = get_indexer(projection)
    indexed = await indexer.index(chunk_ids)
    
    return {"indexed": indexed}

async def ingest_pipeline_handler(params: dict) -> dict:
    root_path = params["root_path"]
    
    # Orchestrate: scan → parse → chunk → index
    scan_result = await scan_handler({"root_path": root_path})
    
    total_chunks = 0
    for doc_id in scan_result["documents"]:
        parse_result = await parse_handler({"document_id": doc_id})
        chunk_result = await chunk_handler({"revision_id": parse_result["revision_id"]})
        await index_handler({"chunk_ids": chunk_result["chunk_ids"]})
        total_chunks += chunk_result["chunks"]
    
    return {
        "scanned": scan_result["scanned"],
        "chunks": total_chunks,
        "indexed": total_chunks,
    }

# Register
handlers = {
    "task:scan": scan_handler,
    "task:parse": parse_handler,
    "task:chunk": chunk_handler,
    "task:index": index_handler,
    "pipeline:ingest": ingest_pipeline_handler,
}

executor = MemoryExecutor(handlers=handlers)
dispatcher = Dispatcher(executor=executor)
```

---

## WorkSpec Types for Document-Spine

| Kind | Name | Purpose |
|------|------|---------|
| `task` | `scan` | Scan directory for documents |
| `task` | `parse` | Parse single document (PDF, MD, code) |
| `task` | `chunk` | Chunk revision into segments |
| `task` | `index` | Index chunks to projection |
| `task` | `rebuild` | Rebuild projection from canonical |
| `pipeline` | `ingest` | Full scan → parse → chunk → index |
| `workflow` | `batch_ingest` | Process multiple directories |

---

## Key Files to Modify

| File | Change |
|------|--------|
| `cli/__init__.py` | Replace direct execution with `dispatcher.submit()` |
| `models/ingestion.py` | Optionally keep for backward compat, store in `RunRecord.result` |
| `integrations/spine_core.py` | Wire `Pipeline` to Dispatcher |
| `ingestion/scanner.py` | Wrap in `scan` handler |
| `ingestion/chunker.py` | Wrap in `chunk` handler |
| `projections/sqlite_fts.py` | Wrap in `index` handler |
| (new) `handlers.py` | Handler registration |

---

## API Endpoints

Add REST API for document processing:

```python
from fastapi import APIRouter
from spine.execution.fastapi import create_runs_router

router = APIRouter()

@router.post("/ingest")
async def start_ingest(request: IngestRequest, dispatcher: Dispatcher):
    run_id = await dispatcher.submit_pipeline("document_spine.ingest", {
        "root_path": request.path,
        "patterns": request.patterns,
        "chunk_size": request.chunk_size,
    })
    return {"run_id": run_id}

# Mount unified /runs API
app.include_router(create_runs_router(dispatcher), prefix="/api/v1")
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                 Document-Spine + spine-core                     │
│                                                                 │
│  ┌──────────┐    ┌────────────┐    ┌──────────────────────────┐│
│  │ CLI/API  │───▶│ Dispatcher │───▶│ Executor                 ││
│  └──────────┘    └────────────┘    │  • MemoryExecutor (dev)  ││
│                        │           │  • CeleryExecutor (prod) ││
│                        ▼           └──────────────────────────┘│
│                 ┌────────────┐                │                 │
│                 │ RunRecord  │◄───────────────┘                 │
│                 │ (replaces  │                                  │
│                 │ IngestionRun)│                                │
│                 └────────────┘                                  │
│                        │                                        │
│                        ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Document-Spine Handlers                      │  │
│  │   scan  │  parse  │  chunk  │  index  │  ingest_pipeline │  │
│  └──────────────────────────────────────────────────────────┘  │
│                        │                                        │
│                        ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  CANONICAL STORE                          │  │
│  │     Documents  │  Revisions  │  Chunks  │  Facts         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Benefits

1. **Resumable Processing:** RunRecord with checkpointing
2. **Progress Tracking:** Real-time progress via events
3. **Parallel Processing:** Fan-out document parsing to workers
4. **Unified Status:** Same API for all document operations
5. **Retry Logic:** Automatic retry for failed parses
