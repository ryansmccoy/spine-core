# Current File Tree — As-Built Layout

> Generated: January 2026 | Status: Post Phase 1-4 Consolidation

This document shows the current file structure with layer annotations.

## Legend

| Layer | Color | Description |
|-------|-------|-------------|
| **FRAMEWORK** | 🔧 | Generic execution infrastructure (spine-core) |
| **DOMAIN** | 📊 | FINRA-specific business logic (spine-domains) |
| **APP** | ⚡ | Commands, services, models (market_spine/app) |
| **ADAPTER-CLI** | 🖥️ | CLI presentation layer (market_spine/cli) |
| **ADAPTER-API** | 🌐 | API presentation layer (market_spine/api) |
| **CONFIG** | ⚙️ | Configuration and wiring |

---

## Package: `spine-core` 🔧

**Location:** `packages/spine-core/src/spine/`

```
spine/
├── __init__.py
├── core/                           # 🔧 Platform primitives
│   ├── __init__.py
│   ├── execution.py                # Execution tracking
│   ├── hashing.py                  # Content hashing
│   ├── idempotency.py              # Idempotency helpers
│   ├── manifest.py                 # Work manifest tracking
│   ├── quality.py                  # Quality event recording
│   ├── rejects.py                  # Reject sink
│   ├── rolling.py                  # Rolling metrics
│   ├── schema.py                   # Core table schemas
│   ├── storage.py                  # Storage utilities
│   └── temporal.py                 # Week/date utilities
│
└── framework/                      # 🔧 Execution framework
    ├── __init__.py
    ├── db.py                       # Connection provider injection
    ├── dispatcher.py               # Execution dispatcher
    ├── exceptions.py               # Framework exceptions
    ├── params.py                   # Parameter validation
    ├── registry.py                 # Pipeline registry
    ├── runner.py                   # Pipeline runner
    ├── logging/                    # Structured logging
    │   ├── __init__.py
    │   ├── config.py
    │   ├── context.py
    │   └── timing.py
    └── pipelines/                  # Pipeline base class
        ├── __init__.py
        └── base.py
```

**Ownership:** Generic, tier-agnostic. NO domain logic (FINRA, tiers, etc.).

---

## Package: `spine-domains` 📊

**Location:** `packages/spine-domains/src/spine/domains/`

```
spine/domains/
├── __init__.py
└── finra/
    ├── __init__.py
    └── otc_transparency/           # 📊 FINRA OTC domain
        ├── __init__.py
        ├── calculations.py         # Aggregation, rolling metrics
        ├── connector.py            # FINRA file parsing
        ├── normalizer.py           # Record validation/normalization
        ├── pipelines.py            # Pipeline implementations
        ├── schema.py               # Tier enum, TABLES, TIER_ALIASES
        └── docs/                   # Domain documentation
            ├── data_dictionary.md
            ├── overview.md
            ├── pipelines.md
            └── timing_and_clocks.md
```

**Ownership:** FINRA-specific business logic. Tier definitions, table schemas, calculations.

---

## Package: `market-spine-basic`

**Location:** `market-spine-basic/src/market_spine/`

### Root Level ⚙️

```
market_spine/
├── __init__.py
├── config.py                       # ⚙️ Environment configuration
└── db.py                           # ⚙️ SQLite connection provider
```

### App Layer ⚡

```
market_spine/app/
├── __init__.py
├── models.py                       # ⚡ Shared dataclasses (Result, ErrorCode, etc.)
│
├── commands/                       # ⚡ Use case orchestration
│   ├── __init__.py
│   ├── executions.py               # RunPipelineCommand
│   ├── pipelines.py                # ListPipelinesCommand, DescribePipelineCommand
│   └── queries.py                  # QueryWeeksCommand, QuerySymbolsCommand
│
└── services/                       # ⚡ Reusable business services
    ├── __init__.py
    ├── data.py                     # DataSourceConfig (table names)
    ├── ingest.py                   # IngestResolver (file path derivation)
    ├── params.py                   # ParameterResolver (merge + normalize)
    └── tier.py                     # TierNormalizer (alias resolution)
```

### CLI Layer 🖥️

```
market_spine/cli/
├── __init__.py                     # Typer app wiring
├── console.py                      # Rich console + get_tier_values()
├── logging_config.py               # CLI log configuration
├── params.py                       # ⚠️ ParamParser (DUPLICATE of app/services/params.py)
├── ui.py                           # Rich panels, tables, formatting
├── README.md                       # CLI documentation
├── UX_GUIDE.md                     # UX guidelines
│
├── commands/                       # CLI command handlers
│   ├── __init__.py
│   ├── db.py                       # init, reset
│   ├── doctor.py                   # health check
│   ├── list_.py                    # pipelines list/describe
│   ├── query.py                    # weeks, symbols
│   ├── run.py                      # pipeline execution
│   └── verify.py                   # table, data verification
│
└── interactive/                    # ⚠️ Interactive mode (uses subprocess)
    ├── __init__.py
    ├── menu.py                     # Main menu loop
    └── prompts.py                  # Parameter prompts
```

### API Layer 🌐

```
market_spine/api/
├── __init__.py
├── app.py                          # FastAPI app factory
│
└── routes/
    ├── __init__.py
    ├── health.py                   # /health endpoints
    └── v1/
        ├── __init__.py
        ├── capabilities.py         # /v1/capabilities
        └── pipelines.py            # /v1/pipelines, /v1/query/*
```

---

## Summary Statistics

| Layer | Files | Purpose |
|-------|-------|---------|
| spine-core | 18 | Generic framework primitives |
| spine-domains | 6 | FINRA OTC business logic |
| app/commands | 3 | Use case orchestration |
| app/services | 4 | Reusable business services |
| app/models | 1 | Shared data models |
| cli | 12 | CLI presentation |
| api | 5 | API presentation |
| config | 2 | Wiring/configuration |

**Total Python files:** ~51 (excluding tests and `__pycache__`)

---

## Layer Dependency Rules

```
┌─────────────────────────────────────────────────────────────┐
│                    ADAPTERS (CLI / API)                      │
│  Can import: app/*, spine.framework, spine.domains          │
│  Cannot export to: anything                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    APP (commands / services)                 │
│  Can import: spine.framework, spine.domains, market_spine.db│
│  Cannot import: cli/*, api/*                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    SPINE.FRAMEWORK                           │
│  Can import: spine.core, spine.domains (lazy loading only)  │
│  Cannot import: market_spine.*                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    SPINE.DOMAINS                             │
│  Can import: spine.core, spine.framework                    │
│  Cannot import: market_spine.*                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    SPINE.CORE                                │
│  Can import: stdlib only (no spine.*, no market_spine.*)    │
└─────────────────────────────────────────────────────────────┘
```
