# Package Ownership

> **Purpose**: Define clear ownership rules for what belongs in each package, ensuring proper separation of concerns across the system.

---

## Package Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           MARKET SPINE SYSTEM                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────────┐  │
│  │   spine-core    │  │  spine-domains  │  │       market-spine-*           │  │
│  │                 │  │                 │  │                                 │  │
│  │  Framework      │  │  Domain Logic   │  │  Tier-specific Implementations  │  │
│  │  Execution      │  │  Pipelines      │  │  CLI / API / UI                 │  │
│  │  Registry       │  │  Calculations   │  │  Storage backends               │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────────┘  │
│                                                                                  │
│         SHARED LIBRARY              SHARED LIBRARY          TIER PACKAGES       │
│         (no IO/storage)             (no storage)            (complete apps)     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## spine-core

### Purpose

**Framework infrastructure** that is domain-agnostic and tier-agnostic. This is the execution engine and orchestration foundation.

### What Belongs Here

| Component | Examples | Rationale |
|-----------|----------|-----------|
| **Pipeline base class** | `Pipeline`, `PipelineResult`, `PipelineStatus` | All pipelines inherit from this |
| **Parameter framework** | `PipelineSpec`, `ParamDef`, validators | Parameter definition and validation |
| **Registry** | `@register_pipeline`, `get_pipeline`, `list_pipelines` | Pipeline discovery mechanism |
| **Runner** | `PipelineRunner` | Synchronous execution |
| **Dispatcher** | `Dispatcher`, `Execution`, `Lane`, `TriggerSource` | Execution coordination |
| **Exceptions** | `PipelineNotFoundError`, `BadParamsError` | Framework-level errors |
| **Logging** | `get_logger`, `log_step`, structured logging | Cross-cutting concern |
| **Core primitives** | `IdempotencyHelper`, `WorkManifest`, `RejectSink`, `QualityRunner` | Reusable infrastructure patterns |

### What Does NOT Belong Here

| Anti-pattern | Why Not | Where It Goes |
|--------------|---------|---------------|
| FINRA-specific logic | Domain-specific | `spine-domains` |
| SQLite connection | Tier-specific storage | `market-spine-basic` |
| Postgres connection | Tier-specific storage | `market-spine-intermediate` |
| CLI commands | UI concern | `market-spine-*` |
| API endpoints | UI concern | `market-spine-*` |
| Tier normalization | Domain-specific | `spine-domains` or `market-spine-*` |
| Environment configuration | Deployment-specific | `market-spine-*` |

### Import Rules

```python
# spine-core can import from:
import structlog  # ✅ External libraries only

# spine-core CANNOT import from:
import spine.domains  # ❌ Would create circular dependency
import market_spine   # ❌ Tier packages depend on core, not vice versa
```

### Package Dependencies

```
spine-core:
  dependencies:
    - structlog
    - pydantic (for ParamDef, etc.)
  no dependencies on:
    - spine-domains
    - market-spine-*
    - database drivers
```

---

## spine-domains

### Purpose

**Domain-specific business logic and pipelines** that are shareable across all tiers. This is where the FINRA OTC transparency logic lives.

### What Belongs Here

| Component | Examples | Rationale |
|-----------|----------|-----------|
| **Pipeline implementations** | `IngestWeekPipeline`, `NormalizeWeekPipeline` | Business logic orchestration |
| **Calculations** | `aggregate_to_symbol_level`, `compute_rolling_metrics` | Pure computational logic |
| **Normalizers** | `normalize_records`, tier enumeration | Data transformation |
| **Connectors** | `parse_finra_file`, `get_file_metadata` | Data parsing (not storage) |
| **Schemas** | `Tier`, `TABLES`, `DOMAIN`, `STAGES` | Domain-specific constants |
| **Validators** | `validate_week_ending`, `validate_tier` | Domain-specific validation |

### What Does NOT Belong Here

| Anti-pattern | Why Not | Where It Goes |
|--------------|---------|---------------|
| `get_connection()` | Storage is tier-specific | `market-spine-*` |
| `CREATE TABLE` statements | DDL is tier-specific | `market-spine-*` migrations |
| CLI presentation | UI concern | `market-spine-*` |
| API serialization | UI concern | `market-spine-*` |

### Import Rules

```python
# spine-domains can import from:
from spine.framework.registry import register_pipeline  # ✅ Core framework
from spine.framework.pipelines import Pipeline          # ✅ Core framework
from spine.framework.db import get_connection           # ✅ DB abstraction (injected)

# spine-domains CANNOT import from:
import sqlite3              # ❌ Specific driver
import asyncpg              # ❌ Specific driver
import market_spine         # ❌ Tier-specific
```

### Storage Abstraction

Domains use the `spine.framework.db` abstraction:

```python
# In spine.framework.db
_connection_provider: Callable[[], Connection] | None = None

def set_connection_provider(provider: Callable[[], Connection]) -> None:
    """Set the connection provider (called by tier packages)."""
    global _connection_provider
    _connection_provider = provider

def get_connection() -> Connection:
    """Get database connection (provider must be set)."""
    if _connection_provider is None:
        raise RuntimeError("No connection provider configured")
    return _connection_provider()
```

Tier packages inject the appropriate provider:

```python
# market-spine-basic: SQLite
from market_spine.db import get_sqlite_connection
from spine.framework.db import set_connection_provider
set_connection_provider(get_sqlite_connection)

# market-spine-intermediate: Postgres
from market_spine_intermediate.db import get_postgres_connection
set_connection_provider(get_postgres_connection)
```

---

## market-spine-basic

### Purpose

**Complete application** for the Basic tier: SQLite-backed, synchronous, single-user reference implementation.

### What Belongs Here

| Component | Examples | Rationale |
|-----------|----------|-----------|
| **SQLite database** | `db.py`, connection management, migrations | Tier-specific storage |
| **CLI** | Typer app, commands, Rich UI | Tier-specific interface |
| **API** | FastAPI app, routes, Pydantic models | Tier-specific interface |
| **Command layer** | `app/commands/`, `app/services/` | Shared between CLI and API |
| **Configuration** | `config.py`, environment settings | Deployment configuration |
| **Migrations** | SQL files in `migrations/` | Schema evolution |

### Folder Structure

```
market-spine-basic/
├── src/market_spine/
│   ├── __init__.py
│   ├── config.py              # Settings (SQLite path, etc.)
│   ├── db.py                  # SQLite connection provider
│   │
│   ├── app/                   # Command layer (CLI + API share this)
│   │   ├── __init__.py
│   │   ├── commands/          # Use case implementations
│   │   │   ├── pipelines.py
│   │   │   ├── executions.py
│   │   │   ├── queries.py
│   │   │   ├── verify.py
│   │   │   └── doctor.py
│   │   ├── services/          # Shared services
│   │   │   ├── tier.py
│   │   │   ├── params.py
│   │   │   └── ingest.py
│   │   └── models.py          # Shared data structures
│   │
│   ├── cli/                   # CLI adapter
│   │   ├── __init__.py
│   │   ├── console.py
│   │   ├── ui.py
│   │   ├── params.py          # CLI-specific param parsing
│   │   ├── commands/
│   │   │   ├── run.py
│   │   │   ├── list_.py
│   │   │   ├── query.py
│   │   │   ├── verify.py
│   │   │   ├── db.py
│   │   │   └── doctor.py
│   │   └── interactive/
│   │       ├── menu.py
│   │       └── prompts.py
│   │
│   └── api/                   # API adapter (future)
│       ├── __init__.py
│       ├── main.py            # FastAPI app
│       ├── routes/
│       │   ├── pipelines.py
│       │   ├── executions.py
│       │   ├── queries.py
│       │   └── health.py
│       └── models.py          # API-specific Pydantic models
│
├── migrations/
│   ├── 001_core_tables.sql
│   └── 020_otc_tables.sql
│
└── tests/
```

### Import Rules

```python
# market-spine-basic can import from:
from spine.framework.dispatcher import Dispatcher  # ✅ Core framework
from spine.framework.registry import list_pipelines  # ✅ Core framework
from spine.domains.finra.otc_transparency import *  # ✅ Domain logic
import sqlite3  # ✅ Tier-specific driver

# Internally:
from market_spine.app.commands.pipelines import ListPipelinesCommand
from market_spine.cli.ui import render_panel
```

---

## Future: market-spine-intermediate

### Purpose

**Postgres-backed, async execution** with job queues and background workers.

### What Changes from Basic

| Aspect | Basic | Intermediate |
|--------|-------|--------------|
| Database | SQLite | Postgres/TimescaleDB |
| Execution | Synchronous | Async (Celery/Dramatiq) |
| API execution | Blocking | Non-blocking + polling |
| Configuration | File-based | Environment + secrets |
| Deployment | Single process | Multiple workers |

### What Stays the Same

- `spine-core` framework (identical)
- `spine-domains` pipelines (identical)
- Command layer interface (same contracts)
- API contracts (same endpoints, different execution)

### New Components

```
market-spine-intermediate/
├── src/market_spine_intermediate/
│   ├── db.py                  # Postgres connection
│   ├── worker.py              # Background job worker
│   ├── tasks.py               # Celery/Dramatiq tasks
│   │
│   ├── app/                   # Same command layer structure
│   │   └── commands/
│   │       └── executions.py  # Returns immediately, queues job
│   │
│   ├── cli/                   # Adapted for async
│   │   └── commands/
│   │       └── run.py         # Shows progress, polls for completion
│   │
│   └── api/                   # Same routes, async handlers
│       └── routes/
│           └── executions.py  # Returns 202 Accepted + polling URL
```

---

## Future: market-spine-advanced

### Purpose

**Multi-user, authenticated** with RBAC, audit logging, and scheduling.

### What Changes from Intermediate

| Aspect | Intermediate | Advanced |
|--------|--------------|----------|
| Auth | None | API keys / OAuth |
| Authorization | None | RBAC (roles, permissions) |
| Multi-user | Single context | User-scoped executions |
| Audit | Basic logging | Full audit trail |
| Scheduling | None | Cron-like scheduling |

### New Components

```
market-spine-advanced/
├── src/market_spine_advanced/
│   ├── auth/                  # Authentication
│   │   ├── api_keys.py
│   │   ├── oauth.py
│   │   └── middleware.py
│   │
│   ├── authz/                 # Authorization
│   │   ├── rbac.py
│   │   ├── permissions.py
│   │   └── policies.py
│   │
│   ├── audit/                 # Audit logging
│   │   ├── events.py
│   │   └── storage.py
│   │
│   ├── scheduler/             # Job scheduling
│   │   ├── cron.py
│   │   └── triggers.py
```

---

## Future: spine-api (Potential New Package)

### Consideration

Should there be a **shared API package** that provides common API infrastructure?

### Arguments For

- Shared request/response models
- Common middleware (auth, logging)
- Reusable route patterns
- Single source of OpenAPI contracts

### Arguments Against

- Premature abstraction
- Tiers have different auth mechanisms
- API is thin enough to duplicate
- Keeping it in tier packages is simpler

### Current Recommendation

**Do NOT create spine-api yet.** 

The API layer is intentionally thin (just an adapter over commands). Any shared patterns can be extracted later when the need becomes clear. Creating it now would be speculative.

If a shared API package is ever needed, it would contain:
- Response model base classes
- Error formatting utilities
- Health check patterns
- OpenAPI customization

---

## Ownership Rules Summary

### Decision Tree

```
Is it about HOW pipelines are executed?
├── Yes → spine-core (framework)
└── No
    │
    Is it domain-specific business logic?
    ├── Yes → spine-domains
    └── No
        │
        Is it about user interface (CLI/API)?
        ├── Yes → market-spine-{tier}
        └── No
            │
            Is it about storage or deployment?
            └── Yes → market-spine-{tier}
```

### Quick Reference

| Question | Answer |
|----------|--------|
| Where does `Pipeline` base class go? | `spine-core` |
| Where does `IngestWeekPipeline` go? | `spine-domains` |
| Where does `get_sqlite_connection` go? | `market-spine-basic` |
| Where does `normalize_tier` go? | `market-spine-basic/app/services/` |
| Where does the CLI command `run.py` go? | `market-spine-basic/cli/commands/` |
| Where does the API route go? | `market-spine-basic/api/routes/` |
| Where does the `RunPipelineCommand` go? | `market-spine-basic/app/commands/` |
| Where does `compute_rolling_metrics` go? | `spine-domains` |
| Where does `Execution` dataclass go? | `spine-core` (dispatcher module) |

### Package Dependency Graph

```
                    ┌─────────────┐
                    │ spine-core  │
                    └──────┬──────┘
                           │
                           │ depends on
                           ▼
                    ┌──────────────┐
                    │ spine-domains │
                    └──────┬───────┘
                           │
                           │ depends on
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
   │ market-spine │ │ market-spine │ │ market-spine │
   │    -basic    │ │-intermediate │ │  -advanced   │
   └──────────────┘ └──────────────┘ └──────────────┘
```

**Note:** Arrows point from dependency to dependent. `spine-core` has no dependencies on other Spine packages.
