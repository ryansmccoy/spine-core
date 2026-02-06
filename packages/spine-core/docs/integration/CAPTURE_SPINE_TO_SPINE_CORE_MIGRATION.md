# Spine-Core vs Capture-Spine: Gap Analysis & Migration Plan

## Goal

**Replace capture-spine's orchestration with spine-core**, and migrate any missing features from capture-spine INTO spine-core so all apps can use it.

---

## Feature Comparison

| Feature | Capture-Spine | Spine-Core | Gap |
|---------|---------------|------------|-----|
| **Dispatcher** | ✅ `Dispatcher` class | ✅ `Dispatcher` class | Same pattern |
| **WorkSpec** | ✅ `Execution` model | ✅ `WorkSpec` + `RunRecord` | Need schema alignment |
| **Status Enum** | ✅ `ExecutionStatus` | ✅ `RunStatus` | Same values |
| **Lane/Priority** | ✅ `Lane` enum | ✅ `priority` + `lane` fields | Same concept |
| **Events** | ✅ `ExecutionEvent` | ✅ `RunEvent` | Same pattern |
| **Backend Protocol** | ✅ `PipelineBackend` | ✅ `Executor` protocol | Same interface |
| **Celery Backend** | ✅ `CeleryBackend` | ⚠️ `CeleryExecutor` (stub) | **Need real impl** |
| **Database Persistence** | ✅ PostgreSQL tables | ❌ In-memory only | **MAJOR GAP** |
| **Concurrency Guard** | ✅ DB unique constraint | ❌ Not implemented | **MAJOR GAP** |
| **Error Types** | ✅ Custom exceptions | ❌ Generic exceptions | Need migration |
| **Invariants/Guards** | ✅ `invariants.py` | ❌ Not implemented | Need migration |
| **Cancel** | ✅ Full cancel flow | ✅ Basic cancel | Same |
| **Retry** | ✅ `retry_count`, `max_retries` | ✅ `attempt`, `retry_of_run_id` | Same |
| **Progress** | ✅ Events | ✅ Events | Same |
| **Heartbeat** | ✅ `HEARTBEAT` event | ⚠️ Not in `EventType` | Need to add |
| **Multi-Backend** | ⚠️ Protocol only | ⚠️ Protocol only | Both need impls |

---

## MAJOR GAPS: What Spine-Core Needs

### Gap 1: Database Persistence (RunLedger)

**Capture-spine has:** PostgreSQL tables (`executions`, `execution_events`)

**Spine-core has:** In-memory dict only (`self._memory_runs`)

**Fix:** Implement `PostgresLedger` that matches capture-spine's schema

```python
# spine-core needs this
class PostgresLedger:
    """Persistent run storage using PostgreSQL."""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def save_run(self, run: RunRecord) -> None:
        """INSERT/UPDATE to runs table."""
        ...
    
    async def get_run(self, run_id: str) -> RunRecord | None:
        """SELECT from runs table."""
        ...
    
    async def list_runs(self, **filters) -> list[RunSummary]:
        """SELECT with filters."""
        ...
    
    async def record_event(self, event: RunEvent) -> None:
        """INSERT to run_events table."""
        ...
```

### Gap 2: Concurrency Guard

**Capture-spine has:** DB unique constraint prevents duplicate active executions
```sql
CREATE UNIQUE INDEX ix_executions_one_active_per_feed 
ON executions (feed_id) 
WHERE status IN ('pending', 'running');
```

**Spine-core has:** Nothing

**Fix:** Add `ConcurrencyGuard` protocol and implementation

```python
# spine-core needs this
class ConcurrencyGuard(Protocol):
    """Prevent duplicate active runs for same entity."""
    
    async def acquire(self, entity_type: str, entity_id: str) -> bool:
        """Try to acquire lock. Returns False if already running."""
        ...
    
    async def release(self, entity_type: str, entity_id: str) -> None:
        """Release lock when run completes."""
        ...

class PostgresConcurrencyGuard(ConcurrencyGuard):
    """Uses DB constraint like capture-spine."""
    ...

class RedisConcurrencyGuard(ConcurrencyGuard):
    """Uses Redis SETNX for distributed locking."""
    ...
```

### Gap 3: Real Celery Executor

**Capture-spine has:** Working `CeleryBackend` with queue routing
```python
class CeleryBackend(PipelineBackend):
    def submit(self, execution_id, pipeline, params, lane):
        # Routes to correct queue based on lane
        task = run_pipeline.apply_async(
            args=[str(execution_id)],
            queue=self._get_queue_for_lane(lane),
        )
        return task.id
```

**Spine-core has:** Stub only
```python
class CeleryExecutor:  # NOT IMPLEMENTED
    pass
```

**Fix:** Port capture-spine's `CeleryBackend` to spine-core

### Gap 4: Error Types

**Capture-spine has:**
```python
class ConcurrencyError(OrchestrationError): ...
class BackendError(OrchestrationError): ...
class PipelineNotFoundError(OrchestrationError): ...
class ExecutionNotFoundError(OrchestrationError): ...
class BackpressureError(OrchestrationError): ...
```

**Spine-core has:** None of these

**Fix:** Add `spine.execution.errors` module

### Gap 5: Heartbeat Event

**Capture-spine has:** `EventType.HEARTBEAT`

**Spine-core has:** Not in `EventType` class

**Fix:** Add to `EventType`

---

## Migration Plan

### Phase 1: Enhance spine-core (1-2 weeks)

| Task | Description | Effort |
|------|-------------|--------|
| 1.1 | Add `PostgresLedger` class | Medium |
| 1.2 | Add `ConcurrencyGuard` protocol + Postgres impl | Medium |
| 1.3 | Port `CeleryBackend` → `CeleryExecutor` | Medium |
| 1.4 | Add error types module | Small |
| 1.5 | Add `HEARTBEAT` to `EventType` | Tiny |
| 1.6 | Add SQL migrations for tables | Medium |

### Phase 2: Align Schemas (few hours)

**Map capture-spine → spine-core:**

| Capture-Spine | Spine-Core |
|---------------|------------|
| `Execution.execution_id` | `RunRecord.run_id` |
| `Execution.pipeline_name` | `WorkSpec.name` |
| `Execution.params` | `WorkSpec.params` |
| `Execution.lane` | `WorkSpec.lane` |
| `Execution.trigger_source` | `WorkSpec.trigger_source` |
| `Execution.status` | `RunRecord.status` |
| `Execution.backend_task_id` | `RunRecord.external_ref` |
| `Execution.feed_id` | `WorkSpec.metadata["feed_id"]` |
| `Execution.retry_count` | `RunRecord.attempt - 1` |

### Phase 3: Replace in capture-spine (1 week)

```python
# BEFORE (capture-spine's own dispatcher)
from app.orchestration import get_dispatcher
dispatcher = get_dispatcher()
execution = await dispatcher.submit("feed_processing", params)

# AFTER (spine-core)
from spine.execution import Dispatcher
from spine.execution.executors import CeleryExecutor
from spine.execution.ledgers import PostgresLedger

ledger = PostgresLedger(pool)
executor = CeleryExecutor(celery_app)
dispatcher = Dispatcher(executor=executor, ledger=ledger)

run_id = await dispatcher.submit_pipeline("feed_processing", params)
```

### Phase 4: Delete capture-spine's orchestration (after validation)

Remove:
- `capture-spine/app/orchestration/` (entire directory)
- `capture-spine/app/orchestration/backends/` (all backends)

Keep spine-core as the single source.

---

## SQL Schema Migration

spine-core needs these tables (based on capture-spine):

```sql
-- runs table (replaces capture-spine's executions)
CREATE TABLE runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(20) NOT NULL,          -- task | pipeline | workflow | step
    name VARCHAR(100) NOT NULL,         -- handler/pipeline name
    params JSONB DEFAULT '{}',
    
    -- Routing
    priority VARCHAR(20) DEFAULT 'normal',
    lane VARCHAR(50) DEFAULT 'default',
    
    -- Tracking
    idempotency_key VARCHAR(255),
    correlation_id VARCHAR(255),
    parent_run_id UUID REFERENCES runs(run_id),
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    external_ref VARCHAR(255),          -- Celery task_id, etc.
    executor_name VARCHAR(50),
    
    -- Results
    result JSONB,
    error TEXT,
    error_type VARCHAR(100),
    
    -- Retry
    attempt INTEGER DEFAULT 1,
    retry_of_run_id UUID REFERENCES runs(run_id),
    max_retries INTEGER DEFAULT 3,
    
    -- Context
    trigger_source VARCHAR(50) DEFAULT 'api',
    metadata JSONB DEFAULT '{}',
    tags JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    
    -- Indexes
    CONSTRAINT uq_idempotency UNIQUE (idempotency_key)
);

-- Concurrency guard index (like capture-spine)
CREATE UNIQUE INDEX ix_runs_one_active_per_entity
ON runs ((metadata->>'entity_type'), (metadata->>'entity_id'))
WHERE status IN ('pending', 'queued', 'running');

-- run_events table
CREATE TABLE run_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(run_id),
    event_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT now(),
    data JSONB DEFAULT '{}',
    source VARCHAR(50) DEFAULT 'dispatcher'
);

CREATE INDEX ix_run_events_run_id ON run_events(run_id);
```

---

## File Structure After Migration

```
spine-core/packages/spine-core/src/spine/execution/
├── __init__.py
├── dispatcher.py           # (enhanced)
├── spec.py                 # WorkSpec
├── runs.py                 # RunRecord, RunStatus
├── events.py               # RunEvent, EventType
├── errors.py               # NEW: ConcurrencyError, etc.
├── registry.py             # HandlerRegistry
├── fastapi.py              # FastAPI integration
├── executors/
│   ├── __init__.py
│   ├── protocol.py         # Executor protocol
│   ├── memory.py           # MemoryExecutor (testing)
│   ├── local.py            # LocalExecutor (threads)
│   ├── celery.py           # CeleryExecutor (ENHANCED)
│   ├── dagster.py          # (future)
│   ├── prefect.py          # (future)
│   └── temporal.py         # (future)
├── ledgers/                # NEW DIRECTORY
│   ├── __init__.py
│   ├── protocol.py         # Ledger protocol
│   ├── memory.py           # MemoryLedger (default)
│   └── postgres.py         # PostgresLedger (production)
├── guards/                 # NEW DIRECTORY
│   ├── __init__.py
│   ├── protocol.py         # ConcurrencyGuard protocol
│   ├── memory.py           # MemoryGuard (testing)
│   ├── postgres.py         # PostgresGuard (production)
│   └── redis.py            # RedisGuard (distributed)
└── migrations/             # NEW DIRECTORY
    ├── 001_runs_table.sql
    └── 002_run_events_table.sql
```

---

## Benefits of Migration

1. **Single Source:** All apps use same execution library
2. **Tested Patterns:** capture-spine's battle-tested patterns in shared lib
3. **Reduced Duplication:** No more separate orchestration per app
4. **Easier Onboarding:** Learn one pattern, use everywhere
5. **Shared Improvements:** Bug fixes benefit all apps

---

## Questions Before Starting

1. **Database:** Should each app have its own `runs` table, or one shared table?
2. **Celery:** Should spine-core depend on Celery, or keep it optional?
3. **Migrations:** Should spine-core own the SQL migrations, or just provide them?
4. **Backwards Compat:** Need migration script for existing `executions` → `runs`?
