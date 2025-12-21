# spine-core — Primitives & Execution Model

## Overview

spine-core is the runtime backbone of the Spine ecosystem. It provides the execution
model, workflow orchestration, run lifecycle tracking, registry, events, artifacts,
and temporal tooling that every downstream service (feedspine, entityspine, …) builds on.

---

## Core Primitives

### The Three-Layer Hierarchy

Understanding spine-core starts with knowing what each primitive *is for*:

```
Layer        What it holds           Who writes it
──────────────────────────────────────────────────────
Operation     Business logic          Domain engineers
Step         A reference + policy    Workflow authors
Workflow     Execution order (DAG)   Workflow authors
```

**Only `Operation` contains actual code.** `Step` and `Workflow` are pure
orchestration — they declare *what* to run and *in what order*, but contain
no logic themselves. This separation means you can test a operation in
isolation, then compose it into workflows without touching it.

---

### Operation

A `Operation` is the **only place business logic lives**. It is a named,
registered, reusable unit that does exactly one thing.

```
Operation (abstract)
├── name: str           – unique registered name  (e.g. "sec.ingest.8k")
├── description: str
├── spec: OperationSpec  – typed parameter declaration
├── params: dict        – runtime parameters (validated against spec)
└── run() → OperationResult
```

Defining a operation:

```python
from spine.framework.operations import Operation, OperationResult, OperationStatus
from spine.framework.registry import register_operation

@register_operation("sec.ingest.8k")
class Ingest8K(Operation):
    """Download and store all 8-K filings for a given date."""

    def run(self) -> OperationResult:
        date = self.params["date"]
        records = fetch_filings(date, form_type="8-K")
        store(records)
        return OperationResult(
            status=OperationStatus.COMPLETED,
            started_at=...,
            metrics={"records": len(records)},
        )
```

A Operation is designed to be:
- **Testable in isolation** — `Ingest8K(params={"date": "2025-01-10"}).run()`
- **Reusable** — referenced by name from any Workflow
- **Discoverable** — `list_operations()` returns all registered names

**Evidence:** [`src/spine/framework/operations/base.py`](../src/spine/framework/operations/base.py) — `class Operation(ABC)`, `class OperationResult`; [`src/spine/framework/registry.py`](../src/spine/framework/registry.py) — `@register_operation`

---

### Step

A `Step` is a **pointer inside a Workflow** — it names a Operation (or inline
function) and attaches per-step execution policy. A Step contains no logic.

```
Step.operation("ingest", "sec.ingest.8k")
      │               └── name of registered Operation
      └── step name (for logging, context, skipping)
```

Five step variants:

| Factory | Logic source | Reusable? |
|---|---|---|
| `Step.operation(name, "registered.name")` | Registered Operation class | ✅ Yes |
| `Step.lambda_(name, fn)` | Inline Python callable | ❌ Inline only |
| `Step.from_function(name, fn)` | Plain function, auto-adapted | ❌ Inline only |
| `Step.choice(name, condition, then_step, else_step)` | Conditional branch | — |
| `Step.wait(name, seconds)` | Pause execution | — |
| `Step.map(name, items, iterator)` | Fan-out / fan-in | — |

Each Step also carries:
- `ErrorPolicy` (STOP or CONTINUE on failure)
- `RetryPolicy` (max_retries + backoff)
- `depends_on` — explicit DAG edges for parallel execution

> **When to use `Step.lambda_` vs `Step.operation`:**
> Use `lambda_` for glue logic that is specific to this workflow (e.g.
> "validate the output of the previous step"). Use `operation` for any
> logic that could be called from more than one workflow — write it as a
> registered Operation first.

**Evidence:** [`src/spine/orchestration/step_types.py`](../src/spine/orchestration/step_types.py) — `class Step`, `class StepType`, `class ErrorPolicy`

---

### Workflow

A `Workflow` is a **named, ordered graph of Steps** with an `ExecutionPolicy`.

```python
Workflow(
    name="finra.weekly_refresh",
    domain="finra.otc_transparency",
    steps=[
        Step.operation("ingest",     "finra.otc_transparency.ingest_week"),
        Step.lambda_("validate",    validate_fn),
        Step.operation("normalize",  "finra.otc_transparency.normalize_week"),
    ],
    execution_policy=WorkflowExecutionPolicy(
        mode=ExecutionMode.SEQUENTIAL,   # or PARALLEL
        timeout_seconds=3600,
        on_failure=FailurePolicy.STOP,
    ),
)
```

- `Workflow` is the **blueprint** — it describes *what* to run.
- `WorkflowRunner` is the **executor** — it describes *how* to run it.
- `TrackedWorkflowRunner` adds DB persistence and observability.

**Evidence:** [`src/spine/orchestration/workflow.py`](../src/spine/orchestration/workflow.py) — module docstring, `class Workflow`

---

### WorkflowContext

An immutable context object passed between steps. Steps can read params,
store outputs, and communicate results without shared mutable state.

**Evidence:** [`src/spine/orchestration/workflow_context.py`](../src/spine/orchestration/workflow_context.py)

---

### Runner

`WorkflowRunner.execute(workflow, params)` is the main entry point:

```
WorkflowRunner.execute(workflow, params)
  │
  ├─ SEQUENTIAL mode: step-by-step, passes context forward
  │
  └─ PARALLEL mode: builds DAG, runs independent steps concurrently
         (ThreadPoolExecutor, capped by max_concurrency)
```

Returns a `WorkflowResult` with `status`, `completed_steps`, `error_step`, and per-step timing.

**Evidence:** [`src/spine/orchestration/workflow_runner.py`](../src/spine/orchestration/workflow_runner.py) — `class WorkflowRunner`, `class WorkflowStatus`

---

### HandlerRegistry

Decouples handler **registration** (at import/startup) from **resolution** (at dispatch time).

```python
# Register
@register_operation("sec.ingest")
async def ingest(params): ...

# Resolve
handler = registry.get("operation", "sec.ingest")
```

Supports global singleton plus injectable instances for testing.
Decorators: `register_task`, `register_operation`, `register_workflow`, `register_step`.

**Evidence:** [`src/spine/execution/registry.py`](../src/spine/execution/registry.py) — `class HandlerRegistry`

---

## Execution Model

### Runs

Every execution is backed by a `RunRecord` — the canonical state machine:

```
PENDING → QUEUED → RUNNING → COMPLETED (terminal)
                           ↘ FAILED → DEAD_LETTERED → PENDING (retry)
                           ↘ CANCELLED (terminal)
```

`RunStatus.DEAD_LETTERED` = retries exhausted, item moved to DLQ.

**Evidence:** [`src/spine/execution/runs.py`](../src/spine/execution/runs.py) — `class RunStatus`, `class RunRecord`

### Execution Ledger

`ExecutionLedger` is the single source of truth for all executions. It manages:

- `core_executions` table — state machine
- `core_execution_events` table — append-only event log

```
ExecutionLedger
├── create_execution(execution) → Execution
├── update_status(id, status)
├── record_event(id, EventType)
└── list_executions(filters)
```

Status→Event mapping: `PENDING→CREATED`, `RUNNING→STARTED`, `COMPLETED→COMPLETED`, `FAILED→FAILED`.

**Evidence:** [`src/spine/execution/ledger.py`](../src/spine/execution/ledger.py) — architecture diagram, `class ExecutionLedger`

### TrackedExecution Context Manager

```python
async with TrackedExecution(
    ledger=ledger, guard=guard, dlq=dlq,
    workflow="sec.filings", params={...},
) as ctx:
    result = await do_work(ctx.params)
    ctx.set_result(result)
```

Lifecycle:
1. Check idempotency key (skip if already done)
2. Create execution in ledger
3. Acquire concurrency lock
4. Mark RUNNING → yield ctx
5. Mark COMPLETED on success / FAILED + DLQ on exception
6. Release lock (always)

**Evidence:** [`src/spine/execution/context.py`](../src/spine/execution/context.py) — module docstring, SequenceDiagram

---

## Replay & Idempotency

All executions carry an `idempotency_key`. The `ExecutionLedger.get_by_idempotency_key()`
call skips re-execution for work already completed with the same key.

For replay from failed state:
- DLQ items can be re-queued: `DEAD_LETTERED → PENDING`
- The retry path is explicit via `RunStatus` transition graph

**Evidence:** `src/spine/execution/runs.py` — `RUN_VALID_TRANSITIONS`; `src/spine/core/idempotency.py`

---

## Events

The event bus (`InMemoryEventBus` or `RedisEventBus`) follows publish/subscribe with
glob-pattern matching:

```python
await bus.subscribe("run.*", handler)          # all run events
await bus.publish(Event(event_type="run.completed", ...))
```

Handlers run concurrently via `asyncio.gather`. Handler errors are logged but
do not stop delivery to other subscribers.

**Evidence:** [`src/spine/core/events/memory.py`](../src/spine/core/events/memory.py) — `class InMemoryEventBus`; [`src/spine/core/events/redis.py`](../src/spine/core/events/redis.py)

---

## Quality Framework

`QualityRunner` executes declarative checks and writes results to `core_quality`:

```python
runner = QualityRunner(conn, domain="otc", execution_id="abc")
runner.add(QualityCheck("share_sum", QualityCategory.BUSINESS_RULE, check_fn))
results = runner.run_all(context, partition_key)
if runner.has_failures():
    raise QualityGateError(runner.failures())
```

Categories: `INTEGRITY`, `COMPLETENESS`, `BUSINESS_RULE`.
Statuses: `PASS`, `WARN`, `FAIL`.

**Evidence:** [`src/spine/core/quality.py`](../src/spine/core/quality.py) — module docstring, `class QualityRunner`

---

## Feature Flags

Thread-safe, pluggable feature flag registry. Flags can be toggled per environment
without code changes. Supports typed variants (bool, string, percentage rollout).

**Evidence:** [`src/spine/core/feature_flags.py`](../src/spine/core/feature_flags.py)

---

## Secrets

`SecretBackend` ABC with pluggable implementations (env vars, Vault, AWS SSM).
Never hardcode secrets — resolve via `get_secret("name")` which dispatches to
the registered backend.

**Evidence:** [`src/spine/core/secrets.py`](../src/spine/core/secrets.py)

---

## Temporal Primitives

See [temporal.md](temporal.md) for the full temporal model.

Quick reference:
- `WeekEnding` — validated Friday value object for weekly financial workflows
- `TemporalEnvelope[T]` — wraps any payload with 4 timestamps
- `BiTemporalRecord` — full bi-temporal fact storage

---

## Summary Diagram

```
             ┌──────────────────────────────────┐
             │           Workflow               │
             │  steps: [Step, Step, ...]        │
             │  policy: sequential|parallel     │
             └──────────────┬───────────────────┘
                            │ execute(params)
                            ▼
             ┌──────────────────────────────────┐
             │         WorkflowRunner           │
             │  runnable: Dispatcher            │
             └──────────────┬───────────────────┘
                            │ per step
                      ┌─────┴──────┐
                      ▼            ▼
              ┌────────────┐  ┌──────────────┐
              │  Operation  │  │  Lambda fn   │
              │ (registry) │  │  (inline)    │
              └─────┬──────┘  └──────┬───────┘
                    │                │
                    └──────┬─────────┘
                           ▼
             ┌──────────────────────────────────┐
             │       ExecutionLedger            │
             │  core_executions                 │
             │  core_execution_events           │
             └──────────────────────────────────┘
```
