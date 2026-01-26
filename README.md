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

## Docker Quick Start

### Starting the Stack

```powershell
# Start basic tier (SQLite, fastest startup)
.\scripts\docker-start.ps1

# Start with a specific tier
.\scripts\docker-start.ps1 -Tier basic         # SQLite
.\scripts\docker-start.ps1 -Tier intermediate  # PostgreSQL
.\scripts\docker-start.ps1 -Tier full          # TimescaleDB + Redis

# With hot-reload for development
.\scripts\docker-start.ps1 -Tier basic -Dev

# Stop the stack
.\scripts\docker-start.ps1 -Tier basic -Down
```

### Cleanup

```powershell
# Stop all containers
.\scripts\docker-cleanup.ps1

# Stop and prune unused resources
.\scripts\docker-cleanup.ps1 -Prune

# Nuclear option - remove everything
.\scripts\docker-cleanup.ps1 -All
```

### Port Assignments

| Service | Basic | Intermediate | Full |
|---------|-------|--------------|------|
| Frontend | 3100 | 3100 | 3100 |
| API | 8100 | 8100 | 8100 |
| PostgreSQL | - | 5432 | - |
| TimescaleDB | - | - | 5432 |
| Redis | - | - | 6379 |

## License

MIT
