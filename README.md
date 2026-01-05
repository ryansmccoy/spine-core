# Spine

> **Thin Domains, Thick Platform** — A modular analytics pipeline framework

Spine is a framework for building temporal data pipelines with structured logging, idempotency tracking, and data lineage. It separates platform infrastructure from business logic, enabling the same domain code to run across different tiers (Basic/SQLite → Full/distributed).

---

## Repository Structure

```
spine/
├── packages/                    # Shared packages (pip-installable)
│   ├── spine-core/              # Platform primitives (framework, execution, logging)
│   └── spine-domains/           # Domain logic (FINRA OTC Transparency, etc.)
│
├── market-spine-basic/          # Basic tier application (SQLite, CLI, FastAPI)
├── market-spine-intermediate/   # Intermediate tier (PostgreSQL, async) [planned]
├── market-spine-advanced/       # Advanced tier (Celery tasks) [planned]
├── market-spine-full/           # Full tier (Event-driven) [planned]
│
└── docs/                        # Cross-cutting documentation
```

---

## Import Direction (Dependency Rules)

```
┌─────────────────────────────────────────────────────────────────┐
│                    APPLICATION TIER                              │
│               (market-spine-basic, etc.)                        │
│                                                                  │
│  CLI / API  →  Commands  →  Services                            │
└─────────────────────┬───────────────────────────────────────────┘
                      │ imports
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FRAMEWORK LAYER                                │
│                  (spine.framework)                               │
│                                                                  │
│  Dispatcher  →  Runner  →  Registry  →  Pipelines               │
└─────────────────────┬───────────────────────────────────────────┘
                      │ imports
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DOMAIN LAYER                                  │
│         (spine.domains.finra.otc_transparency, etc.)            │
│                                                                  │
│  Pipelines  →  Calculations  →  Normalizer  →  Schema           │
└─────────────────────┬───────────────────────────────────────────┘
                      │ imports
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CORE LAYER                                    │
│                   (spine.core)                                   │
│                                                                  │
│  Manifest  │  Rejects  │  Quality  │  Temporal                  │
└─────────────────────────────────────────────────────────────────┘
```

**Rules:**
- ✅ App imports Framework, Domain, Core
- ✅ Framework imports Domain, Core
- ✅ Domain imports Core only
- ❌ Domain NEVER imports Framework or App
- ❌ Core NEVER imports anything above it
- ❌ Domain NEVER imports infrastructure (`sqlite3`, `asyncpg`, `requests`, etc.)

---

## Key Concepts

### Execution Records

Every pipeline run creates an **Execution** with:
- `execution_id`: UUID identifying the run
- `batch_id`: Groups related executions
- `trigger_source`: How it was started (cli, api, scheduler)
- `lane`: Priority/processing lane (normal, backfill, slow)

### Idempotency Model

Pipelines are **idempotent by partition key**. Running the same pipeline with the same parameters:
1. Checks the manifest for existing completion
2. Skips if already processed (unless forced)
3. Records new completion in manifest

### Manifest / Quality / Rejects

| Concept | Table | Purpose |
|---------|-------|---------|
| **Manifest** | `core_manifest` | Tracks workflow stage completion |
| **Quality** | `core_quality` | Records quality check results |
| **Rejects** | `core_rejects` | Stores validation failures with reasons |

### Three-Clock Temporal Model

| Clock | Field | Meaning |
|-------|-------|---------|
| **Business Time** | `week_ending` | The business period the data represents |
| **Source Time** | `last_update_date` | When the source published the data |
| **Capture Time** | `captured_at` | When we ingested the data |

---

## Quick Start (Basic Tier)

```bash
# Clone and enter the repo
cd market-spine-basic

# Install with uv (recommended)
uv sync

# Initialize database
uv run spine db init

# Run a pipeline
uv run spine run run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1 \
  --file data/fixtures/otc/week_2025-12-26.psv

# Query results
uv run spine query weeks --tier NMS_TIER_1

# Start API server
uv run uvicorn market_spine.api.app:app --host 0.0.0.0 --port 8000
```

See [market-spine-basic/README.md](market-spine-basic/README.md) for full documentation.

---

## Development Tools

### Command Runners

Spine supports multiple command runners for different workflows:

#### Python Scripts (Always Available)
```bash
# Direct Python execution
python scripts/build_schema.py
uv run spine db init
pytest tests/
```

#### Just (Recommended - Cross-platform)
**Install:** https://github.com/casey/just
- Windows: `scoop install just` or `choco install just`
- macOS: `brew install just`
- Linux: `cargo install just`

```bash
just schema-build    # Build schema from modules
just db-init         # Initialize database
just test            # Run tests
just lint            # Run linter
just --list          # Show all commands
```

#### Make (Unix/macOS)
```bash
make schema-build    # Build schema from modules
make test            # Run tests
make lint            # Run linter
make help            # Show all targets
```

#### Docker Compose
```bash
# Build schema
docker compose --profile schema run --rm schema-build

# Initialize database
docker compose run --rm db-init

# Start API server
docker compose up api
# API at http://localhost:8000
# Docs at http://localhost:8000/docs

# Run pipeline
docker compose run --rm spine spine run <pipeline> -p key=value
```

### Schema Management

The schema is now **modular** - split by package ownership:

```
packages/
├── spine-core/src/spine/core/schema/
│   └── 00_core.sql                    # Core framework tables
└── spine-domains/src/spine/domains/
    ├── finra/otc_transparency/schema/
    │   ├── 00_tables.sql              # FINRA tables
    │   ├── 01_indexes.sql             # FINRA indexes
    │   └── 02_views.sql               # FINRA views
    └── reference/exchange_calendar/schema/
        ├── 00_tables.sql              # Reference tables
        └── 01_indexes.sql             # Reference indexes
```

**Workflow:**
```bash
# 1. Edit schema module
vim packages/spine-core/src/spine/core/schema/00_core.sql

# 2. Build combined schema
just schema-build  # or: python scripts/build_schema.py

# 3. Validate
pytest tests/test_schema_modules.py -v

# 4. Apply to database
just db-reset

# 5. Commit both files
git add packages/*/src/*/schema/*.sql
git add market-spine-basic/migrations/schema.sql
git commit -m "feat(schema): Add new table"
```

**Documentation:**
- [Schema Module Architecture](docs/architecture/SCHEMA_MODULE_ARCHITECTURE.md)

---

## API Documentation

Market Spine provides both a **Control Plane** (operations API) and a **Data Plane** (query API). Full documentation is in `docs/api/`:

| Document | Purpose |
|----------|---------|
| [00-api-overview.md](docs/api/00-api-overview.md) | Architecture, terminology, stable contract philosophy |
| [01-data-access-patterns.md](docs/api/01-data-access-patterns.md) | Query patterns, pagination, response envelopes |
| [02-basic-api-surface.md](docs/api/02-basic-api-surface.md) | Complete Basic tier endpoint reference |
| [03-intermediate-advanced-full-roadmap.md](docs/api/03-intermediate-advanced-full-roadmap.md) | API evolution by tier |
| [04-openapi-and-testing-strategy.md](docs/api/04-openapi-and-testing-strategy.md) | OpenAPI conventions, testing approach |

### Quick API Reference (Basic Tier)

**Control Plane:**
- `GET /health` — Liveness check
- `GET /v1/capabilities` — Feature flags
- `GET /v1/pipelines` — List pipelines
- `POST /v1/pipelines/{name}/run` — Execute pipeline

**Data Plane:**
- `GET /v1/data/weeks` — Available weeks by tier
- `GET /v1/data/symbols` — Top symbols for a week

See the [frontend integration guide](docs/frontend-backend-integration-map.md) for client adaptation strategies.

---

## Package Documentation

| Package | Description | README |
|---------|-------------|--------|
| **spine-core** | Platform primitives (execution, logging, manifest) | [packages/spine-core/README.md](packages/spine-core/README.md) |
| **spine-domains** | Domain logic (FINRA OTC, etc.) | [packages/spine-domains/README.md](packages/spine-domains/README.md) |
| **market-spine-basic** | Basic tier application | [market-spine-basic/README.md](market-spine-basic/README.md) |

---

## Design Principles

### 1. Sync-Only Primitives

All `spine.core` and `spine.framework` primitives are **synchronous**. Higher tiers provide adapters:

```python
# Basic tier - native sync (SQLite)
conn = sqlite3.connect("spine.db")

# Intermediate tier - async driver with sync adapter
conn = SyncPgAdapter(await asyncpg.connect(...))
```

### 2. Domain Purity

Domains contain **only business logic**. They cannot import infrastructure modules:
- ❌ `sqlite3`, `asyncpg`, `psycopg2`
- ❌ `celery`, `redis`
- ❌ `boto3`, `requests`

Verify with: `uv run pytest tests/test_domain_purity.py`

### 3. Pydantic at Boundary Only

Pydantic models are used ONLY at API boundaries. Internal code uses:
- Dataclasses for command requests/responses
- TypedDicts or plain dicts for pipeline parameters
- Domain-specific enums and types

---

## What Guarantees Market Spine Provides

These guarantees are **enforced by tests** in `test_fitness.py`:

| Guarantee | Description | Enforcement |
|-----------|-------------|-------------|
| **Idempotency** | Same inputs + version = same outputs | Determinism tests |
| **Auditability** | Every output row traces to source via `capture_id` | Schema constraints |
| **Non-destructive** | Replays create new captures, never overwrite | DELETE + INSERT pattern |
| **Version safety** | `get_current_version()` handles v10 > v2 correctly | Registry tests |
| **Deprecation visibility** | Deprecated versions warn, never silently serve | Deprecation surfacing |
| **Invariant validation** | Shares sum to 1.0, ranks consecutive | Invariant tests |
| **Fail-loud** | Missing data raises clear errors, never silent | Stress tests |
| **Registry contracts** | Current ≠ deprecated, versions never removed | Contract tests |

### Verified by Tests

```bash
# Run all fitness tests (currently 30+ tests)
cd market-spine-basic
uv run pytest tests/test_fitness.py -v

# Key test classes:
# - TestUniquenessConstraints: DB constraints work
# - TestReplayIdempotency: DELETE + INSERT is safe
# - TestCalcVersionRegistry: Registry contracts enforced
# - TestDeterminism: Audit fields excluded from comparison
# - TestVenueShareCalc: Business invariants hold
# - TestMissingDataBehavior: Fail-loud guarantees
```

See [docs/fitness/README.md](docs/fitness/README.md) for detailed documentation.

---

## Development

### Run Tests

```bash
cd market-spine-basic
uv run pytest tests/ -v
```

### Run Smoke Test

```bash
cd market-spine-basic
uv run python scripts/smoke_test.py
```

### Lint and Format

```bash
uv run ruff check src tests
uv run ruff format src tests
```

---

## Release Checklist

1. ✅ Run tests: `uv run pytest tests/ -v`
2. ✅ Run smoke test: `uv run python scripts/smoke_test.py`
3. ✅ Run linter: `uv run ruff check src tests`
4. ✅ Verify domain purity: `uv run pytest tests/test_domain_purity.py`
5. ✅ Update version in `pyproject.toml`
6. ✅ Update CHANGELOG (if exists)

---

## License

MIT
