# GenAI-Spine Integration Guide

## Overview

GenAI-Spine is a **synchronous request-response API service** with no background job infrastructure. All AI work happens inline during HTTP requests. This makes it ideal for adding async/batch capabilities via spine-core.

---

## Current Execution Patterns

| Pattern | Location | Description |
|---------|----------|-------------|
| **FastAPI Server** | `__main__.py` | Uvicorn entry point |
| **Capabilities** | `capabilities/` | Summarize, Extract, Classify, Rewrite |
| **Providers** | `providers/` | Ollama, OpenAI, Anthropic LLM backends |
| **Tracking** | `services/tracking.py` | Usage/cost tracking |

---

## What's Missing

- ❌ **No Celery** or task queue
- ❌ **No scheduler** 
- ❌ **No background workers**
- ❌ **No batch processing** endpoints
- ❌ **No pipeline orchestration**

---

## Integration Opportunities

### 1. Batch Processing → Workflow

**Current:** Single-item endpoints only

**Unified:**
```python
# Submit batch summarization
run_id = await dispatcher.submit_workflow("genai.batch_summarize", {
    "texts": [text1, text2, text3, ...],
    "model": "claude-3-sonnet",
    "max_tokens": 500,
})

# Poll for results
run = await dispatcher.get_run(run_id)
# run.result = {"summaries": [...], "total_tokens": 5000, "cost": 0.15}
```

### 2. Pipeline Execution → WorkSpec

**Current:** `TODO: Pipeline execution engine` in codebase

**Unified:**
```python
# Define multi-step AI pipeline
run_id = await dispatcher.submit_pipeline("genai.rag_pipeline", {
    "query": "What is the company's revenue?",
    "documents": ["10k_2025.pdf", "10q_q3.pdf"],
    "steps": ["embed", "retrieve", "generate"],
})
```

### 3. Long-Running Generation → Async Task

**Current:** Blocking request for large generations

**Unified:**
```python
# Submit long generation
run_id = await dispatcher.submit_task("genai.completion", {
    "prompt": large_prompt,
    "model": "claude-3-opus",
    "max_tokens": 10000,
}, priority="low", lane="gpu")

# Return immediately
return {"run_id": run_id, "status": "queued"}

# Client polls GET /runs/{run_id} for result
```

### 4. Cost Aggregation → Scheduled Task

**Current:** On-demand aggregation

**Unified:**
```python
# Daily cost rollup
run_id = await dispatcher.submit_task("genai.aggregate_costs", {
    "period": "daily",
    "date": "2026-01-15",
}, idempotency_key="cost_rollup_2026-01-15")
```

### 5. Execute-Prompt → Dispatcher

**Current:** `POST /execute-prompt` runs inline

**Unified:**
```python
@router.post("/execute-prompt")
async def execute_prompt(request: PromptRequest, dispatcher: Dispatcher):
    run_id = await dispatcher.submit_task("genai.execute_prompt", {
        "prompt_id": request.prompt_id,
        "variables": request.variables,
    })
    
    # For sync clients, wait for result
    if request.wait:
        run = await dispatcher.wait(run_id, timeout=30)
        return run.result
    
    return {"run_id": run_id}
```

---

## Handler Registration

```python
from spine.execution import HandlerRegistry
from spine.execution.executors import MemoryExecutor

# Define handlers
async def completion_handler(params: dict) -> dict:
    prompt = params["prompt"]
    model = params.get("model", "claude-3-sonnet")
    result = await provider.complete(prompt, model=model)
    return {
        "text": result.text,
        "tokens": result.usage.total_tokens,
        "cost": result.cost,
    }

async def summarize_handler(params: dict) -> dict:
    text = params["text"]
    result = await summarize_capability.run(text)
    return {"summary": result.summary, "tokens": result.tokens}

async def extract_handler(params: dict) -> dict:
    text = params["text"]
    schema = params.get("schema")
    result = await extract_capability.run(text, schema=schema)
    return {"entities": result.entities}

async def batch_summarize_handler(params: dict) -> dict:
    texts = params["texts"]
    results = []
    for text in texts:
        result = await summarize_capability.run(text)
        results.append(result.summary)
    return {"summaries": results, "count": len(results)}

async def rag_pipeline_handler(params: dict) -> dict:
    query = params["query"]
    documents = params["documents"]
    
    # Step 1: Embed query
    query_embedding = await embed(query)
    
    # Step 2: Retrieve relevant chunks
    chunks = await retrieve(query_embedding, documents)
    
    # Step 3: Generate answer
    answer = await generate(query, chunks)
    
    return {"answer": answer, "sources": chunks}

# Register
handlers = {
    "task:completion": completion_handler,
    "task:summarize": summarize_handler,
    "task:extract": extract_handler,
    "workflow:batch_summarize": batch_summarize_handler,
    "pipeline:rag_pipeline": rag_pipeline_handler,
}

executor = MemoryExecutor(handlers=handlers)
dispatcher = Dispatcher(executor=executor)
```

---

## WorkSpec Types for GenAI-Spine

| Kind | Name | Purpose |
|------|------|---------|
| `task` | `completion` | Raw LLM completion |
| `task` | `summarize` | Text summarization |
| `task` | `extract` | Entity extraction |
| `task` | `classify` | Content classification |
| `task` | `rewrite` | Content rewriting |
| `task` | `embed` | Generate embeddings |
| `task` | `execute_prompt` | Run stored prompt template |
| `task` | `aggregate_costs` | Daily cost rollup |
| `workflow` | `batch_summarize` | Parallel summarization |
| `workflow` | `batch_extract` | Parallel extraction |
| `pipeline` | `rag_pipeline` | Embed → Retrieve → Generate |

---

## Key Files to Modify

| File | Change |
|------|--------|
| `api/routers/capabilities.py` | Add async dispatch option |
| `api/routers/completions.py` | Add batch endpoint |
| `services/tracking.py` | Add scheduled aggregation |
| `capabilities/*.py` | Wrap as handler functions |
| (new) `tasks/handlers.py` | Handler registration |
| (new) `tasks/celery.py` | Celery configuration |

---

## Priority and Lane Routing

```python
# High-priority user-facing request (wait for result)
run_id = await dispatcher.submit_task("genai.summarize", 
    {"text": text},
    priority="realtime",
)

# GPU-accelerated embedding batch
run_id = await dispatcher.submit_workflow("genai.batch_embed",
    {"texts": large_text_list},
    lane="gpu",
    priority="normal",
)

# Low-priority batch processing
run_id = await dispatcher.submit_workflow("genai.batch_summarize",
    {"texts": texts},
    priority="low",
    lane="batch",
)
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                   GenAI-Spine + spine-core                      │
│                                                                 │
│  ┌──────────┐    ┌────────────┐    ┌──────────────────────────┐│
│  │ API      │───▶│ Dispatcher │───▶│ Executor                 ││
│  │ Endpoints│    └────────────┘    │  • MemoryExecutor (dev)  ││
│  └──────────┘          │           │  • CeleryExecutor (prod) ││
│                        ▼           │  • GPU queue routing     ││
│                 ┌────────────┐     └──────────────────────────┘│
│                 │ RunRecord  │                │                 │
│                 │ + cost     │◄───────────────┘                 │
│                 └────────────┘                                  │
│                        │                                        │
│                        ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                GenAI-Spine Handlers                       │  │
│  │  completion │ summarize │ extract │ batch_summarize      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                        │                                        │
│                        ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   LLM Providers                           │  │
│  │       Ollama  │  OpenAI  │  Anthropic  │  Azure          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Benefits

1. **Batch Processing:** Process thousands of items without timeout
2. **GPU Routing:** Route embedding tasks to GPU workers
3. **Cost Tracking:** Track costs per run with correlation
4. **Progress Updates:** Long generations report progress
5. **Retry Logic:** Automatic retry for rate limits
6. **Idempotency:** Prevent duplicate expensive LLM calls
