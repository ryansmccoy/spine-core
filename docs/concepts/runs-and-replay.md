# spine-core — Runs, Replay & Artifacts

## Runs

A **Run** is the authoritative record of one unit of execution. It lives in
`core_executions` and has a well-defined state machine.

### `RunStatus` State Machine

```
PENDING
  ├── → QUEUED        (submitted to executor)
  ├── → RUNNING       (synchronous fast path)
  └── → CANCELLED

QUEUED
  ├── → RUNNING
  ├── → COMPLETED     (sync executors finish immediately)
  ├── → FAILED        (executor rejection)
  └── → CANCELLED

RUNNING
  ├── → COMPLETED     ✓ terminal
  ├── → FAILED        ✗
  └── → CANCELLED     ✗ terminal

FAILED
  ├── → DEAD_LETTERED (retries exhausted)
  └── → PENDING       (retry)

DEAD_LETTERED
  └── → PENDING       (manual retry from DLQ)
```

Transitions are **enforced** — `validate_run_transition()` raises if you attempt
an illegal hop.

**Evidence:** [`src/spine/execution/runs.py`](../src/spine/execution/runs.py) — `RUN_VALID_TRANSITIONS`

---

### `RunRecord` Fields

| Field | Type | Notes |
|---|---|---|
| `run_id` | `str` | UUID, primary key |
| `spec` | `WorkSpec` | What to run (handler name + params) |
| `status` | `RunStatus` | Current state |
| `created_at` | `datetime` | Set at creation |
| `started_at` | `datetime` | Set on RUNNING |
| `completed_at` | `datetime` | Set on terminal state |
| `error` | `str` | Error message on FAILED |
| `retry_count` | `int` | Incremented on each retry |
| `idempotency_key` | `str` | Skip if already completed |
| `parent_run_id` | `str` | For sub-runs in workflows |

---

## Execution Ledger

`ExecutionLedger` manages two tables:

```
core_executions              core_execution_events
───────────────              ─────────────────────
id (PK)                      id (PK)
workflow                     execution_id (FK)
params (JSON)                event_type
status                       timestamp
lane                         data (JSON)
trigger_source
parent_execution_id
created_at / started_at / completed_at
result (JSON)
error
retry_count
idempotency_key
```

Events are **append-only** — the full audit trail is preserved even after
the execution reaches a terminal state.

### Key Operations

```python
ledger = ExecutionLedger(conn)
exec   = Execution.create(workflow="sec.ingest")
ledger.create_execution(exec)
ledger.update_status(exec.id, ExecutionStatus.RUNNING)
ledger.record_event(exec.id, EventType.STARTED)
history = ledger.list_executions(workflow="sec.ingest", limit=50)
```

**Evidence:** [`src/spine/execution/ledger.py`](../src/spine/execution/ledger.py) — ER diagram, `class ExecutionLedger`

---

## Idempotency

Pass an `idempotency_key` to `TrackedExecution`. If an execution with the same
key already exists in COMPLETED status, the context manager **skips** re-execution
immediately without touching the executor.

Pattern for safe re-runs:

```python
key = f"sec.ingest:{date}:{cik}"
async with TrackedExecution(
    ...,
    workflow="sec.ingest",
    idempotency_key=key,
) as ctx:
    ...   # skipped if key already completed
```

**Evidence:** `src/spine/execution/context.py` — step 1 in lifecycle comment; `src/spine/core/idempotency.py`

---

## Dead Letter Queue (DLQ)

When retries are exhausted, a run transitions to `DEAD_LETTERED` and a `DeadLetter`
record is created. DLQ items can be:

- **Inspected** via CLI (`spine dlq list`) or API (`GET /api/v1/dlq`)
- **Retried** — moves the item back to `PENDING`
- **Discarded** — marks as resolved without re-running

The DLQ is stored in `core_dead_letters`.

**Evidence:** `src/spine/execution/dlq.py` — `class DLQManager`; `src/spine/api/routers/dlq.py`

---

## Concurrency Guard

`ConcurrencyGuard` prevents duplicate concurrent executions of the same workflow
by acquiring an advisory lock keyed on the workflow name (and optional lane).

- **Acquired** before `RUNNING` is set.
- **Released** in `finally` — always, even on exception.
- Configurable timeout: if the lock can't be acquired within `N` seconds,
  raises `ExecutionLockError`.

**Evidence:** `src/spine/execution/concurrency.py` — `class ConcurrencyGuard`

---

## Artifacts

Artifacts are named byte-blobs associated with a run. Examples:

- Raw downloaded files (SEC filings, FINRA OTC ZIPs)
- Intermediate parquet snapshots
- Quality check reports

```python
# Store
await artifact_store.put(
    run_id="abc-123",
    name="raw/sec_rss_2025-01-10.xml",
    data=response_bytes,
    content_type="application/xml",
)

# Retrieve
data = await artifact_store.get(run_id="abc-123", name="raw/sec_rss_2025-01-10.xml")
```

Backends: local filesystem (`FileSystemArtifactStore`) or cloud object storage.

**Evidence:** `src/spine/core/storage.py` — artifact store interface; `src/spine/framework/sources/file.py`

---

## Scheduling

spine-core includes a pluggable scheduler for recurring runs:

```
ScheduleService
  ├── apscheduler_backend.py  – production (APScheduler)
  ├── celery_backend.py       – distributed (Celery beat)
  └── thread_backend.py       – in-process (testing)
```

Schedules are stored in `core_schedules` and picked up by the active backend.

**Evidence:** `src/spine/core/scheduling/` — multiple backends, `class ScheduleService`

---

## Observability

All executions emit structured log lines via `structlog`. Key log fields:

| Field | Value |
|---|---|
| `execution_id` | UUID |
| `workflow` | e.g. `"sec.ingest"` |
| `status` | current status |
| `duration_ms` | elapsed ms |
| `step` | current step name (workflow runs) |

Metrics are exported via `spine.observability.metrics` (Prometheus-compatible).

**Evidence:** `src/spine/observability/` — `logging.py`, `metrics.py`
