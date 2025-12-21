# Spine-Core

**Canonical execution contract and application framework for the Spine Ecosystem**

Spine-Core provides the foundational modules used across all Spine ecosystem projects including EntitySpine, FeedSpine, GenAI-Spine, Document-Spine, and Capture-Spine.

## Core Modules

| Module | Description |
|--------|-------------|
| **spine.core** | Primitives: Result[T], ExecutionContext, schema, configuration |
| **spine.execution** | WorkSpec, RunRecord, Dispatcher, Executors, Ledger |
| **spine.framework** | Operation registry, runner, logging, alerts |
| **spine.orchestration** | Workflow runner, group runner, tracked runner |

## Features

- **Multi-tier Docker Deployment** — Basic (SQLite), Intermediate (PostgreSQL), Full (TimescaleDB + Redis)
- **Registry Architecture** — Operation registry for automatic source discovery
- **Core Primitives** — ExecutionContext, Result[T] pattern, capture semantics
- **Execution Infrastructure** — Ledger, Concurrency Guard, DLQ Manager

## Quick Links

- [Features](FEATURES.md) — Feature history
- [Changelog](CHANGELOG.md) — Release history

## Principles & Philosophy

Design principles, best practices, and anti-patterns governing the Spine ecosystem.

| Document | Description |
|----------|-------------|
| [Tenets](principles/SPINE_TENETS.md) | 10-item manifesto (60-second read) |
| [Principles](principles/SPINE_PRINCIPLES.md) | 20 core principles with evidence citations |
| [Practices](principles/SPINE_PRACTICES.md) | Best practices, code snippets, and contributor checklists |
| [Anti-Patterns](principles/SPINE_ANTI_PATTERNS.md) | 15 anti-patterns + 7 non-goals |
| [Design Rationale](principles/SPINE_DESIGN_RATIONALE.md) | 15 architectural decision records |
| [Glossary](principles/SPINE_GLOSSARY.md) | 40+ canonical terms |
| [Style Guide](principles/SPINE_STYLE_GUIDE.md) | Naming, module layout, docstrings, testing |

## Project Structure

```
spine-core/
├── src/spine/             # Main package
│   ├── core/              # Primitives, config, schema
│   ├── execution/         # Dispatcher, executors, ledger
│   ├── framework/         # Operations, runner, logging
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
