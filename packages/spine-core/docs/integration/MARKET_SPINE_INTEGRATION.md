# Market-Spine Integration Guide

## Overview

Market-Spine is **the reference implementation** - it already has a unified `dispatch()` pattern with multiple backend support (Celery, Dagster, Prefect, Airflow, Temporal). Use this as a template for other spines.

---

## Current Architecture (Already Unified)

| Component | Location | Description |
|-----------|----------|-------------|
| **Dispatcher** | `orchestrator/dispatcher.py` | `dispatch()` entry point |
| **Backends** | `orchestrator/backends/` | Simple, Celery, Dagster, Prefect, Airflow, Temporal |
| **Pipeline Registry** | `calcs/registry.py` | Named pipelines with specs |
| **Pipeline Engine** | `calcs/engine.py` | Pipeline, Stage, Frame, Calc abstractions |
| **Execution Service** | `services/execution.py` | Central tracking |
| **Task Context** | `pipelines/context.py` | Event-based lifecycle updates |

---

## Architecture Guardrail

> **INV-1:** "All execution triggers MUST flow through orchestrator.dispatch()"

This is exactly what spine-core codifies.

---

## Dispatch Pattern (Reference)

```python
# orchestrator/dispatcher.py
async def dispatch(
    pipeline_name: str,
    params: dict,
    backend: str | None = None,
) -> ExecutionResult:
    """
    THE canonical entry point for all work execution.
    
    - Creates Execution record
    - Routes to configured backend (Celery, Dagster, etc.)
    - Returns result/status
    """
```

---

## Backend Protocol (Reference)

```python
# orchestrator/backends/__init__.py
class ExecutorBackend(Protocol):
    """All backends implement this interface."""
    
    async def submit(
        self,
        execution_id: str,
        pipeline_name: str,
        params: dict,
    ) -> str:
        """Submit work, return external_ref."""
        ...
    
    async def cancel(self, external_ref: str) -> bool:
        """Cancel if possible."""
        ...
    
    async def get_status(self, external_ref: str) -> str:
        """Get runtime status."""
        ...
```

This matches spine-core's `Executor` protocol exactly.

---

## Pipeline Registry (Reference)

```python
# calcs/registry.py
PIPELINES = {
    "ingest_otc": PipelineSpec(
        name="ingest_otc",
        description="FINRA OTC transparency data",
        schedule="0 7 * * 3",  # Wed 7 AM
        timeout=3600,
        stages=["fetch", "parse", "store", "notify"],
    ),
    "compute_otc_metrics": PipelineSpec(
        name="compute_otc_metrics",
        description="Weekly OTC metrics calculation",
        schedule="0 22 * * 1-5",  # 10 PM weekdays
        stages=["load", "calculate", "store"],
    ),
}
```

---

## spine-core Alignment

Market-Spine's patterns directly map to spine-core:

| Market-Spine | spine-core |
|--------------|------------|
| `dispatch()` | `Dispatcher.submit()` |
| `ExecutorBackend` | `Executor` protocol |
| `ExecutionResult` | `RunRecord` |
| `ExecutionStatus` | `RunStatus` |
| `PipelineSpec` | `WorkSpec` |
| `PIPELINES` registry | `HandlerRegistry` |

---

## What Market-Spine Can Teach Other Spines

### 1. Backend Selection via Environment
```python
# Simple configuration
ORCHESTRATOR_BACKEND=simple|celery|dagster|prefect|airflow|temporal

# In code
backend = get_backend(os.environ.get("ORCHESTRATOR_BACKEND", "simple"))
```

### 2. Deprecation Shims for Migration
```python
# jobs/ingest.py - Thin wrapper with deprecation warning
@celery_app.task
def ingest_otc_legacy(week_start: str):
    warnings.warn(
        "Direct task call deprecated. Use dispatch('ingest_otc', {...})",
        DeprecationWarning,
    )
    return _dispatch_pipeline("ingest_otc", {"week_start": week_start})
```

### 3. CLI for Backend Comparison
```bash
# Compare same pipeline across backends
python -m market_spine.orchestrators.cli compare ingest_otc

# Output:
# Backend    | Duration | Status   | Notes
# simple     | 45s      | SUCCESS  | Baseline
# celery     | 48s      | SUCCESS  | +3s queue overhead
# dagster    | 52s      | SUCCESS  | +7s asset materialization
```

### 4. Event-Based Progress Updates
```python
# pipelines/context.py
class TaskContext:
    async def report_progress(self, percent: float, message: str):
        await self.event_bus.publish("execution.progress", {
            "execution_id": self.execution_id,
            "percent": percent,
            "message": message,
        })
```

---

## Opportunities for spine-core Adoption

### 1. Consolidate Dual Orchestrator Modules

**Current:**
- `orchestrator/` (canonical)
- `orchestrators/` (hybrid CLI/migration)

**Unified:** Single `orchestrator/` module

### 2. Complete Legacy Task Migration

**Current:** Deprecation warnings targeting 2026-Q2
```python
# jobs/ingest.py, jobs/calcs.py
warnings.warn("Deprecated, use dispatch()", DeprecationWarning)
```

**Action:** Remove shims after migration complete

### 3. Standardize WorkSpec Schema

**Current:** Custom `ExecutionParams` dataclass

**Unified:** Use spine-core `WorkSpec`
```python
from spine.execution import WorkSpec

spec = WorkSpec(
    kind="pipeline",
    name="ingest_otc",
    params={"week_start": "2026-01-15"},
    priority="normal",
    lane="ingest",
)
```

### 4. Share Backend Implementations

Market-Spine backends can be promoted to spine-core:

```python
# spine.execution.executors.dagster
from spine.execution.executors.protocol import Executor

class DagsterExecutor(Executor):
    """Dagster backend for spine-core."""
    # Market-Spine implementation promoted
```

---

## Key Files to Reference

| Purpose | Location |
|---------|----------|
| Dispatcher pattern | `orchestrator/dispatcher.py` |
| Backend protocol | `orchestrator/backends/__init__.py` |
| Simple backend | `orchestrator/backends/simple.py` |
| Celery backend | `orchestrator/backends/celery_backend.py` |
| Dagster backend | `orchestrator/backends/dagster_backend.py` |
| Pipeline registry | `calcs/registry.py` |
| Pipeline engine | `calcs/engine.py` |
| Task context | `pipelines/context.py` |
| Execution service | `services/execution.py` |
| API routes | `api/v1/executions/router.py` |
| CLI | `orchestrators/cli.py` |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                Market-Spine (Reference Implementation)          │
│                                                                 │
│  ┌──────────┐    ┌────────────┐    ┌──────────────────────────┐│
│  │ API/CLI  │───▶│  dispatch()│───▶│ Backend Selection        ││
│  │ Beat     │    └────────────┘    │  • SimpleBackend (dev)   ││
│  └──────────┘          │           │  • CeleryBackend (prod)  ││
│                        ▼           │  • DagsterBackend        ││
│                 ┌────────────┐     │  • PrefectBackend        ││
│                 │ Execution  │     │  • AirflowBackend        ││
│                 │ (tracking) │     │  • TemporalBackend       ││
│                 └────────────┘     └──────────────────────────┘│
│                        │                      │                 │
│                        ▼                      ▼                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Pipeline Engine                          │  │
│  │   Pipeline  │  Stage  │  Frame  │  Calc                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                        │                                        │
│                        ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Data Stores                             │  │
│  │    TimescaleDB  │  Redis  │  S3                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Lesson for Other Spines

Market-Spine proves the pattern works at scale:

1. **Single Entry Point:** All work goes through `dispatch()`
2. **Backend Abstraction:** Swap runtimes without code changes
3. **Unified Tracking:** One `executions` table for all work
4. **Deprecation Path:** Shims for gradual migration
5. **CLI Tooling:** Backend comparison for validation

**Use Market-Spine as your template when integrating spine-core into other apps.**
