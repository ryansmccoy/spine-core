# Core Concepts Overview

spine-core is organized in **5 layers**, each building on the one below. This page introduces the key abstractions and how they fit together.

## Architecture Layers

```
┌─────────────────────────────────────────────┐
│  Layer 5: Cross-Cutting                     │
│  Quality gates, anomaly tracking, caching,  │
│  feature flags, secrets                     │
├─────────────────────────────────────────────┤
│  Layer 4: Orchestration                     │
│  Workflows, steps, runners, composition,    │
│  playground, templates, LLM integration     │
├─────────────────────────────────────────────┤
│  Layer 3: Execution                         │
│  Dispatcher, executors, retry, circuit      │
│  breaker, rate limiter, DLQ, ledger         │
├─────────────────────────────────────────────┤
│  Layer 2: Database & Storage                │
│  Connection protocol, dialect system,       │
│  base repository, adapters, migrations      │
├─────────────────────────────────────────────┤
│  Layer 1: Type System                       │
│  Result[T], SpineError, ULID, WeekEnding,   │
│  BiTemporalRecord, ExecutionContext         │
└─────────────────────────────────────────────┘
```

## Layer 1: Type System (`spine.core`)

The foundation provides types that flow through every layer:

- **`Result[T]`** — Functional error handling via `Ok`/`Err` instead of exceptions
- **`SpineError`** — Typed exception hierarchy with retry semantics
- **`WeekEnding`** — Friday-aligned temporal anchor for financial calendars
- **`ULID`** — Time-sortable unique identifiers via `generate_ulid()`
- **`ExecutionContext`** — Lineage tracking with batch and execution IDs

## Layer 2: Database & Storage (`spine.core`)

Portable data access across 5 backends:

- **`Connection` protocol** — Sync database interface (`execute`, `fetchone`, `fetchall`)
- **`Dialect`** — SQL generation per backend (SQLite, PostgreSQL, MySQL, DB2, Oracle)
- **`BaseRepository`** — CRUD operations using dialect-aware queries
- **Adapters** — Connection pooling and lifecycle management

## Layer 3: Execution (`spine.execution`)

Infrastructure for running and tracking work:

- **`WorkSpec`** — Describes a unit of work (task, operation, or workflow)
- **`Dispatcher`** — Routes work specs to registered handlers
- **`RetryStrategy`** — Configurable retry with exponential/linear/constant backoff
- **`CircuitBreaker`** — Fail-fast protection against cascading failures
- **`RateLimiter`** — Request throttling (token bucket, sliding window)
- **`DLQManager`** — Dead-letter queue for failed work items
- **`ExecutionLedger`** — Append-only audit log of all execution events

## Layer 4: Orchestration (`spine.orchestration`)

Multi-step workflow composition and execution:

- **`Workflow`** — DAG of steps with execution policies
- **`Step`** — Unit of work (lambda, operation, function, choice, wait, map)
- **`WorkflowRunner`** — Executes workflows with error handling policies
- **`TrackedWorkflowRunner`** — Database-backed execution with checkpointing
- **Composition** — `chain()`, `parallel()`, `conditional()`, `merge_workflows()`
- **`WorkflowPlayground`** — Interactive debugger for development

## Layer 5: Cross-Cutting

Shared concerns that apply across all layers:

- **`QualityRunner`** — Data validation checkpoint framework
- **`AnomalyRecorder`** — Track and query data anomalies
- **`FeatureFlags`** — Runtime toggles with `FlagRegistry`
- **`CacheBackend`** — In-memory and Redis caching
- **`SecretsResolver`** — Pluggable secret backends (env, file, vault)

## Design Principles

1. **Sync-only core** — All primitives use synchronous APIs for simplicity
2. **Zero dependencies** — Core module has no required runtime dependencies
3. **Domain agnostic** — Composable by any domain package
4. **Type safe** — Full type hints throughout, Python 3.12+ features
5. **Schema ownership** — Core owns infrastructure tables, domains own their tables

For the full set of principles, see [Principles](../principles/SPINE_PRINCIPLES.md) and [Tenets](../principles/SPINE_TENETS.md).
