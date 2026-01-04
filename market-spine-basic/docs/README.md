# Market Spine Basic Documentation

Welcome to the documentation for Market Spine Basic — a minimal, CLI-driven analytics pipeline system for market data.

## What is Market Spine Basic?

Market Spine Basic is the **simplest tier** of the Market Spine platform. It demonstrates how to build robust data pipelines using:

- **SQLite** for storage (no servers required)
- **Synchronous execution** (no queues, no workers)
- **CLI interface** (no web UI)
- **Structured logging** for observability

It is designed to be a **teaching tool** and **reference implementation** for the larger Spine ecosystem.

## Who is this for?

- Engineers learning the Spine architecture
- Teams prototyping new data domains
- Anyone who needs a working pipeline system in < 5 minutes

## Documentation Structure

### [Tutorial](tutorial/)

Step-by-step guides to get running:

| Guide | Description |
|-------|-------------|
| [01_quickstart.md](tutorial/01_quickstart.md) | Install, configure, run your first pipeline in 5 minutes |
| [02_running_pipelines.md](tutorial/02_running_pipelines.md) | How to run, monitor, and debug pipelines |

### [Architecture](architecture/)

Deep dives into how things work:

| Document | Description |
|----------|-------------|
| [01_system_overview.md](architecture/01_system_overview.md) | The two-layer architecture: app vs library |
| [02_execution_model.md](architecture/02_execution_model.md) | How pipelines are discovered, dispatched, and executed |
| [03_pipeline_model.md](architecture/03_pipeline_model.md) | Anatomy of a pipeline: stages, primitives, and orchestration |
| [04_logging_and_events.md](architecture/04_logging_and_events.md) | Structured logging for dashboards and debugging |

### [Decisions](decisions/)

Architectural Decision Records (ADRs) explaining *why* things work this way:

| Decision | Description |
|----------|-------------|
| [001_single_dispatch_entrypoint.md](decisions/001_single_dispatch_entrypoint.md) | Why all execution goes through the Dispatcher |
| [002_capture_id_and_versioning.md](decisions/002_capture_id_and_versioning.md) | How we track data provenance with capture_id |
| [003_sqlite_reset_and_dev_workflow.md](decisions/003_sqlite_reset_and_dev_workflow.md) | Why "nuke and rebuild" is the right dev workflow |
| [004_structured_logging_schema.md](decisions/004_structured_logging_schema.md) | The stable event schema for observability |

## Quick Links

- [Project README](../README.md) — Installation and quick start
- [Basic vs Intermediate](BASIC_VS_INTERMEDIATE.md) — Tier comparison
- [Logging Schema](logging-schema.md) — Event format reference for dashboards

## Important Truths (Invariants)

These are the rules that must never be violated:

1. **All pipeline execution goes through the Dispatcher** — No direct instantiation
2. **Domains never import from `market_spine`** — Only from `spine.core`
3. **Business logic lives in `calculations.py`** — Pipelines are orchestrators, not calculators
4. **Pipelines are idempotent** — Running twice with same params produces same result
5. **Every row has lineage** — `execution_id`, `batch_id`, `capture_id` trace every record

## Getting Help

1. Read the [Quickstart](tutorial/01_quickstart.md)
2. Check the [Architecture Overview](architecture/01_system_overview.md)
3. Search the ADRs for the *why* behind decisions
