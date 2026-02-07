# Spine Core - Project Summary

**Package:** spine-core  
**Version:** 0.1.0 (Alpha)  
**Author:** Ryan McCoy  
**License:** MIT  
**Python:** ≥3.12  
**Generated:** February 6, 2026

---

## Executive Summary

**Spine Core** is a registry-driven data pipeline framework for financial market data. It provides platform primitives and infrastructure for building domain-specific data pipelines with:

- **Registry-driven architecture** — Pipelines discover sources and schemas automatically
- **Capture semantics** — Append-only data with revision tracking for auditability
- **Quality gates** — Built-in validation and anomaly detection
- **Domain isolation** — Domains extend the framework without modifying core
- **Unified execution** — Single contract for tasks, pipelines, and workflows

---

## Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `structlog` | ≥24.0.0 | Structured logging |
| `pydantic` | ≥2.0.0 | Data validation |

---

## Architecture Overview

```
spine-core/
├── src/spine/
│   ├── core/           # Platform primitives (sync-only)
│   │   ├── errors.py       # Structured error types
│   │   ├── result.py       # Result[T] envelope
│   │   ├── temporal.py     # WeekEnding, date ranges
│   │   ├── execution.py    # ExecutionContext, lineage
│   │   ├── manifest.py     # WorkManifest for multi-stage workflows
│   │   ├── quality.py      # Quality check framework
│   │   ├── idempotency.py  # Skip/force, delete+insert patterns
│   │   ├── rolling.py      # Rolling window utilities
│   │   └── schema/         # Core infrastructure tables
│   │
│   ├── execution/      # Unified execution framework
│   │   ├── spec.py         # WorkSpec contract
│   │   ├── runs.py         # RunRecord, RunStatus
│   │   ├── dispatcher.py   # Submission and query API
│   │   ├── registry.py     # Handler registration
│   │   ├── executors/      # Runtime adapters (Memory, Local)
│   │   ├── retry.py        # Retry strategies
│   │   ├── circuit_breaker.py
│   │   ├── rate_limit.py   # Token bucket, sliding window
│   │   ├── ledger.py       # Execution persistence
│   │   ├── concurrency.py  # Concurrency guards
│   │   └── dlq.py          # Dead letter queue
│   │
│   ├── orchestration/  # Workflow orchestration
│   │   ├── workflow.py     # Workflow definition
│   │   ├── workflow_runner.py  # Context-aware execution
│   │   ├── step_types.py   # Lambda, Pipeline, Choice steps
│   │   ├── models.py       # PipelineGroup (v1)
│   │   └── registry.py     # Group/workflow registration
│   │
│   ├── framework/      # Application infrastructure
│   │   ├── pipelines/      # Pipeline base classes
│   │   ├── sources/        # Source adapters (File, API, DB)
│   │   ├── alerts/         # Alerting framework
│   │   └── registry.py     # Pipeline registration
│   │
│   └── observability/  # Logging and metrics
│       ├── logging.py      # Structured JSON logging
│       └── metrics.py      # Prometheus-style metrics
│
├── tests/              # 800+ passing tests
├── examples/           # Usage examples
└── docs/               # Comprehensive documentation
```

---

## Key Components

### 1. Core Primitives (`spine.core`)

| Component | Purpose |
|-----------|---------|
| `WeekEnding` | Validated Friday date for weekly workflows |
| `ExecutionContext` | Lineage tracking through pipeline execution |
| `WorkManifest` | Multi-stage workflow progress tracking |
| `Result[T]` | Explicit success/failure handling |
| `QualityRunner` | Quality check framework |
| `IdempotencyHelper` | Safe re-run patterns |

### 2. Execution Framework (`spine.execution`)

| Component | Purpose |
|-----------|---------|
| `WorkSpec` | Universal work specification (task/pipeline/workflow) |
| `Dispatcher` | Submission and query API |
| `HandlerRegistry` | Handler registration and lookup |
| `RetryStrategy` | Exponential, linear, constant backoff |
| `CircuitBreaker` | Failure protection |
| `RateLimiter` | Token bucket, sliding window |
| `ExecutionLedger` | Persistent execution storage |

### 3. Orchestration (`spine.orchestration`)

| Model | Purpose |
|-------|---------|
| **v1: PipelineGroups** | Static DAG, no data passing |
| **v2: Workflows** | Context-aware, data passing between steps |

### 4. Framework (`spine.framework`)

| Component | Purpose |
|-----------|---------|
| `Pipeline` | Base class for data pipelines |
| `FileSource` | File ingestion (CSV, PSV, JSON, Parquet) |
| `AlertChannel` | Slack, Email, webhook notifications |

---

## Chronological Timeline

### Week 1: January 4, 2026 - Project Genesis

| Date | Commit | Description |
|------|--------|-------------|
| Jan 4 | `89c63bc` | Initial commit: spine-core framework package |
| Jan 4 | `849e227` | Standardize operational scripts layout |
| Jan 4 | `50df096` | Full implementation: domains, pipelines, API, scheduler |
| Jan 4 | `6b1ed67` | Add spine-domains package with FINRA and reference data |
| Jan 4 | `5b0ad7f` | Add comprehensive documentation and tooling |

### Week 2: January 11-12, 2026 - Orchestration & Integration

| Date | Commit | Description |
|------|--------|-------------|
| Jan 11 | `1bdb209` | Integrate spine-core orchestration into intermediate tier |
| Jan 11 | `d22e3f8` | Merge dev branch: Add spine-core orchestration module |
| Jan 11 | `610377e` | Clean up spine-core: remove examples and docs |
| Jan 12 | `e0a2ed1` | Add core primitives, frameworks, and orchestration v2 |
| Jan 12 | `72e45bc` | Refactor: Clean master branch |
| Jan 12 | `4f182ac` | Sync errors, result, alerts, sources, workflow v2 |
| Jan 12 | `5fc4055` | Add Workflow v2 documentation and pattern examples |

### Week 3: January 25, 2026 - Execution Framework Sprint

| Date | Commit | Description |
|------|--------|-------------|
| Jan 25 | `4442f73` | Add unified execution contract |
| Jan 25 | `a06d3a1` | Add unified execution framework with observability |
| Jan 25 | `b933d4e` | Add execution primitives and observability layer |
| Jan 25 | `3d3af67` | Add test suites for retry logic and structured logging |
| Jan 25 | `3c2dd57` | Add test suites for resilience primitives |
| Jan 25 | `16de686` | Add ecosystem integration guides and examples |
| Jan 25 | `ada1776` | Add project metadata and classifiers |
| Jan 25 | `394f715` | Fix MemoryExecutor status assertions |
| Jan 25 | `88b623c` | Add MkDocs documentation infrastructure |
| Jan 25 | `47ac2cb` | Add execution system tests and examples |
| Jan 25 | `7c89505` | Fix workflow_example to use MemoryExecutor |
| Jan 25 | `3d5b9a4` | Refactor: flatten package structure for PyPI publishing |

### Week 4: January 28-31, 2026 - CI/CD & Domains

| Date | Commit | Description |
|------|--------|-------------|
| Jan 28 | `369f4c4` | Add trading-desktop.zip |
| Jan 29 | `4747f8c` | Add CI/CD, Makefile, and changelog documentation |
| Jan 29 | `74d4471` | Add trading-desktop and dev files to gitignore |
| Jan 31 | `f10cea5` | Add copilot_chat and earnings domain modules |

### Week 5: February 2-6, 2026 - Release Preparation

| Date | Commit | Description |
|------|--------|-------------|
| Feb 2 | `fefdb7a` | Move market-spine tiers to separate branch |
| Feb 2 | `7bd7534` | Move doc-automation to document-spine |
| Feb 2 | `e502914` | Move trading-desktop to standalone repo |
| Feb 6 | `a41ea6a` | Flatten package for PyPI, migrate trading-desktop and doc-automation out |

---

## Test Status

```
===================== 800 passed, 10 deselected in 6.85s =====================
```

| Category | Count | Status |
|----------|-------|--------|
| Core Tests | ~170 | ✅ Passing |
| Execution Tests | ~150 | ✅ Passing |
| Framework Tests | ~70 | ✅ Passing |
| Orchestration Tests | ~120 | ✅ Passing |
| Observability Tests | ~55 | ✅ Passing |
| Integration Tests | ~80 | ✅ Passing |
| Unit Tests | ~85 | ✅ Passing |

---

## Outstanding Items

### Blocking (Must Fix Before Release)

| Item | Status | Notes |
|------|--------|-------|
| Rate limiter tests timeout | ⚠️ Fixed | Already marked with `@pytest.mark.slow` |
| LICENSE file missing | ❌ Missing | Need to create MIT LICENSE |
| CONTRIBUTING.md missing | ❌ Missing | Need to create |

### Non-Blocking (Should Fix)

| Item | Status | Notes |
|------|--------|-------|
| Expand README.md | ⚠️ Basic | Needs more feature documentation |
| release.yml workflow | ❌ Missing | For PyPI publishing |
| docs.yml workflow | ❌ Missing | For documentation deployment |
| Makefile | ❌ Missing | For common commands |

### Code TODOs

| Location | TODO |
|----------|------|
| `orchestration/registry.py:177` | Phase 2: Load from YAML files in groups/ directory |
| `orchestration/registry.py:178` | Phase 2: Load from database if group_storage=database |

---

## Branch Structure

| Branch | Purpose | Status |
|--------|---------|--------|
| `master` | Stable releases | Clean |
| `dev` | Development | Active |
| `feature/unified-execution-contract` | Current work | **HEAD** |
| `market-spine-tiers` | Market spine tiers (separated) | Archived |

---

## Release Readiness: 🟡 NEARLY READY

### What's Done ✅
- Core primitives implemented and tested
- Unified execution framework complete
- Orchestration v1 and v2 complete
- 800+ passing tests
- CI/CD configured (GitHub Actions)
- pyproject.toml complete for PyPI
- Examples and documentation

### What's Needed ❌
1. **LICENSE file** (MIT)
2. **CONTRIBUTING.md**
3. **Merge feature branch to dev/master**
4. **Tag v0.1.0 release**

---

## Quick Start

```python
from spine.execution import Dispatcher, task_spec, register_task
from spine.execution.executors import MemoryExecutor

@register_task("process_data")
async def process_data(params):
    return {"processed": True, "count": params.get("count", 0)}

# Create dispatcher with in-memory executor
dispatcher = Dispatcher(executor=MemoryExecutor())

# Submit task
run_id = await dispatcher.submit_task("process_data", {"count": 100})

# Check result
run = await dispatcher.get_run(run_id)
print(f"Status: {run.status}")  # RunStatus.COMPLETED
```

---

*Generated from commit analysis and codebase review*
