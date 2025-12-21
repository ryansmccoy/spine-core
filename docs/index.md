# Spine-Core

**Canonical execution contract and application framework for the Spine Ecosystem**

Spine-Core provides the foundational modules used across all Spine ecosystem projects including EntitySpine, FeedSpine, GenAI-Spine, Document-Spine, and Capture-Spine.

## Core Modules

| Module | Description |
|--------|-------------|
| **spine.core** | Primitives: Result[T], ExecutionContext, schema, configuration |
| **spine.execution** | WorkSpec, RunRecord, Dispatcher, Executors, Ledger |
| **spine.framework** | Pipeline registry, runner, logging, alerts |
| **spine.orchestration** | Workflow runner, group runner, tracked runner |

## Features

- **Multi-tier Docker Deployment** — Basic (SQLite), Intermediate (PostgreSQL), Full (TimescaleDB + Redis)
- **Registry Architecture** — Pipeline registry for automatic source discovery
- **Core Primitives** — ExecutionContext, Result[T] pattern, capture semantics
- **Execution Infrastructure** — Ledger, Concurrency Guard, DLQ Manager

## Quick Links

- [Features](FEATURES.md) — Feature history
- [Changelog](CHANGELOG.md) — Release history

## Project Structure

```
spine-core/
├── src/spine/             # Main package
│   ├── core/              # Primitives, config, schema
│   ├── execution/         # Dispatcher, executors, ledger
│   ├── framework/         # Pipelines, runner, logging
│   └── orchestration/     # Workflow and group runners
├── docs/                  # Documentation
├── examples/              # Example code
└── tests/                 # Test suite
```

## Getting Started

1. Clone the repository
2. Install dependencies: `uv sync` or `pip install -e .`
3. Run tests: `uv run pytest tests/`
4. Run examples: `python examples/01_primitives/01_hello_world.py`
