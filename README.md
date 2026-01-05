# Spine Core

A registry-driven data pipeline framework for financial market data.

## Status

🚧 **Under Development** — Not ready for production use.

## Overview

Spine Core provides the foundational framework for building domain-specific data pipelines with:

- **Registry-driven architecture** — Pipelines discover sources and schemas automatically
- **Capture semantics** — Append-only data with revision tracking for auditability  
- **Quality gates** — Built-in validation and anomaly detection
- **Domain isolation** — Domains extend the framework without modifying core

## Structure

```
packages/
  spine-core/     # Framework primitives (registry, dispatcher, base classes)
```

## Development

Active development happens on the `dev` branch.

```bash
git checkout dev
```

## License

MIT
