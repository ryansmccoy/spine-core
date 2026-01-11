# Basic vs Intermediate: Feature Comparison

This document compares the **Basic** and **Intermediate** tiers of Market Spine.

## At a Glance

| Feature | Basic | Intermediate |
|---------|-------|--------------|
| **Database** | SQLite | PostgreSQL |
| **Execution** | Synchronous | Async (anyio) |
| **Scheduling** | Manual / cron | Declarative schedules |
| **UI** | CLI only | CLI + Web dashboard |
| **Deployment** | Single container | Docker Compose |
| **Observability** | Structured logging | Logs + Metrics + Traces |
| **Backfill** | Single-threaded | Parallel workers |

## Basic Tier

**Purpose**: Learning and small-scale production

Basic is designed to be:
- **Simple**: One Python process, one SQLite file
- **Understandable**: All code visible, no magic
- **Portable**: Copy folder anywhere, run immediately

**Use Cases**:
- Learning pipeline patterns
- Personal analytics projects
- Prototyping new domains
- CI/CD testing
- Edge deployments

**Architecture**:
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    CLI      │────▶│  Dispatcher │────▶│   SQLite    │
│  (spine)    │     │   (sync)    │     │  (spine.db) │
└─────────────┘     └─────────────┘     └─────────────┘
```

**What You Get**:
- `spine` CLI for all operations
- Structured logging with execution tracing
- Idempotent pipelines with manifest tracking
- 99+ tests covering edge cases
- Docker deployment ready

## Intermediate Tier

**Purpose**: Production multi-domain workloads

Intermediate adds:
- **Persistence**: Execution state survives restarts
- **Scheduling**: Declarative pipeline schedules
- **Dashboard**: Web UI for monitoring
- **Parallelism**: Background workers for backfills

**Use Cases**:
- Team data platforms
- Multiple domains running concurrently
- Production deployments with SLAs
- Self-service analytics

**Architecture**:
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Web UI    │────▶│   FastAPI   │────▶│ PostgreSQL  │
│             │     │   Server    │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
              ┌──────────┐  ┌──────────┐
              │ Worker 1 │  │ Worker N │
              └──────────┘  └──────────┘
```

**Additional Features**:
- Persistent execution history
- Pipeline schedules (cron-like)
- Web dashboard with live updates
- Multiple workers for parallel execution
- Event-driven triggers

## Shared Components

Both tiers share these packages (in `packages/`):

| Package | Purpose |
|---------|---------|
| `spine-core` | Framework: dispatcher, runner, registry, logging |
| `spine-domains-otc` | OTC domain: FINRA data processing |
| `spine-domains-prices` | Prices domain: OHLCV data (future) |

This means:
- Domain logic works identically in both tiers
- Tests written against Basic work in Intermediate
- Upgrade from Basic to Intermediate by changing infrastructure only

## When to Choose Each

**Choose Basic if**:
- You're learning pipeline patterns
- Single-user or personal project
- Running on laptop/Raspberry Pi
- Need simple deployment (one container)
- Don't need web UI

**Choose Intermediate if**:
- Team needs visibility into pipeline runs
- Multiple domains running concurrently
- Need persistent execution history
- Want declarative scheduling
- Planning to scale to multiple workers

## Migration Path

Migrating from Basic to Intermediate:

1. **Same domain code**: No changes needed to `spine.domains.*`
2. **Same pipelines**: Registration and execution unchanged
3. **Database migration**: Export SQLite → Import to PostgreSQL
4. **Configuration**: Update connection settings
5. **Deploy**: Use docker-compose for multi-container setup

The domain/calculation layer is tier-agnostic by design.

## Summary

| Tier | Complexity | Best For |
|------|------------|----------|
| **Basic** | Low | Learning, prototypes, single-user |
| **Intermediate** | Medium | Teams, production, multi-domain |
| **Advanced** | High | Enterprise, multi-region, real-time |

Start with Basic. Graduate to Intermediate when you need persistence and scheduling. Consider Advanced for enterprise requirements.
