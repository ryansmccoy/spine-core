# Spine-Core

**Core packages, utilities, and shared infrastructure for the Spine Ecosystem**

Spine-Core provides the foundational packages used across all Spine ecosystem projects including EntitySpine, FeedSpine, GenAI-Spine, Document-Spine, and Capture-Spine.

## Packages

| Package | Description |
|---------|-------------|
| **doc-automation** | Extract documentation from source code annotations |
| **config-spine** | Unified configuration management |
| **shared-utils** | Common utilities and helpers |

## Features

- **Multi-tier Docker Deployment** - Basic (SQLite), Intermediate (PostgreSQL), Full (TimescaleDB + Redis)
- **Registry Architecture** - Pipeline registry for automatic source discovery
- **Core Primitives** - ExecutionContext, Result[T] pattern, capture semantics

## Quick Links

- [Features](FEATURES.md) - Feature history
- [Changelog](CHANGELOG.md) - Release history
- [Generated Architecture](generated/ARCHITECTURE.md) - Auto-generated from source annotations
- [Generated API Reference](generated/API_REFERENCE.md) - Auto-generated API docs

## Project Structure

```
spine-core/
├── packages/              # Shared packages
│   ├── doc-automation/    # Documentation extraction
│   ├── config-spine/      # Configuration management
│   └── shared-utils/      # Common utilities
├── docs/                  # Documentation
├── examples/              # Example code
├── scripts/               # Utility scripts
└── tests/                 # Test suite
```

## Getting Started

1. Clone the repository
2. Install dependencies: `pip install -e .`
3. Run examples: `python examples/basic_usage.py`

## Documentation

This documentation is auto-generated from source code annotations using the doc-automation package. Changes to source code annotations will be reflected in the generated documentation on the next build.
