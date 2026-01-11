# Current Layout Snapshot

Generated: 2026-01-03

## Project Structure Overview

```
market-spine-basic/
├── src/market_spine/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── api/                    # FastAPI transport layer
│   │   ├── __init__.py
│   │   ├── app.py              # App factory
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py       # /health, /health/detailed
│   │       └── v1/
│   │           ├── __init__.py
│   │           ├── capabilities.py  # /v1/capabilities
│   │           └── pipelines.py     # /v1/pipelines, /v1/data/*
│   ├── app/                    # Command & service layer
│   │   ├── __init__.py
│   │   ├── models.py           # Shared dataclasses (Result, ErrorCode, etc.)
│   │   ├── commands/
│   │   │   ├── __init__.py
│   │   │   ├── executions.py   # RunPipelineCommand
│   │   │   ├── pipelines.py    # ListPipelinesCommand, DescribePipelineCommand
│   │   │   └── queries.py      # QueryWeeksCommand, QuerySymbolsCommand
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── data.py         # DataSourceConfig (table names)
│   │       ├── ingest.py       # IngestResolver
│   │       ├── params.py       # ParameterResolver
│   │       └── tier.py         # TierNormalizer
│   └── cli/                    # Typer CLI layer
│       ├── __init__.py         # App setup, callback, interactive hook
│       ├── console.py          # Rich console + TIER_VALUES/TIER_ALIASES
│       ├── logging_config.py   # CLI logging setup
│       ├── params.py           # ParamParser (CLI-specific)
│       ├── ui.py               # Rich panels and tables
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── db.py           # db init, db reset
│       │   ├── doctor.py       # Health checks
│       │   ├── list_.py        # pipelines list, pipelines describe
│       │   ├── query.py        # query weeks, query symbols
│       │   ├── run.py          # run run
│       │   └── verify.py       # verify table, verify data
│       └── interactive/
│           ├── __init__.py
│           ├── menu.py         # Questionary-based interactive mode
│           └── prompts.py      # Pipeline parameter prompts
├── tests/
│   ├── __init__.py
│   ├── test_api.py             # FastAPI TestClient tests (25 tests)
│   ├── test_commands.py        # Command unit tests
│   ├── test_dispatcher.py      # Framework integration
│   ├── test_domain_purity.py   # Domain boundary checks
│   ├── test_error_handling.py  # Error code/exit code tests
│   ├── test_ingest_resolver.py # IngestResolver tests
│   ├── test_parameter_resolver.py # ParameterResolver tests
│   ├── test_parity.py          # CLI/API parity tests (4 tests)
│   ├── test_pipelines.py       # Pipeline registry tests
│   ├── test_registry.py        # Registry integrity tests
│   └── test_tier_normalizer.py # TierNormalizer tests
└── docs/
    ├── README.md
    ├── CLI.md
    ├── DEMO.md
    ├── api-cli/
    ├── architecture/
    ├── decisions/
    ├── planning/
    └── tutorial/
```

---

## Layer Responsibilities

### `src/market_spine/api/` — FastAPI Transport Layer

**BELONGS HERE:**
- Pydantic request/response models
- Route handlers that delegate to commands
- HTTP status code mapping
- OpenAPI documentation
- Error response formatting (`{success, error: {code, message}}`)

**MUST NOT BELONG HERE:**
- Business logic
- Direct database access
- Direct registry/framework calls
- Tier normalization (delegate to commands)

---

### `src/market_spine/app/` — Command & Service Layer

#### `app/commands/`

**BELONGS HERE:**
- Request/Result dataclasses (plain Python)
- Command classes that orchestrate operations
- Delegation to services for domain logic
- Error wrapping with `CommandError` and `ErrorCode`

**MUST NOT BELONG HERE:**
- Domain constants (tier values, table names)
- Pydantic models
- CLI or HTTP concerns
- Direct SQL (except queries.py which queries data)

#### `app/services/`

**BELONGS HERE:**
- Stateless utility classes
- Domain logic adapters (TierNormalizer, IngestResolver)
- Data source configuration (DataSourceConfig)
- Parameter resolution and validation

**MUST NOT BELONG HERE:**
- Command orchestration
- CLI/API concerns
- HTTP/response formatting

#### `app/models.py`

**BELONGS HERE:**
- Shared dataclasses (Result, CommandError, ErrorCode)
- Execution models (ExecutionStatus, ExecutionMetrics)
- Pipeline models (PipelineSummary, PipelineDetail, ParameterDef)
- Query result models (WeekInfo, SymbolInfo)

**MUST NOT BELONG HERE:**
- Pydantic models (those are in API layer)
- Domain constants (those are in spine.domains)

---

### `src/market_spine/cli/` — Typer CLI Layer

#### `cli/commands/`

**BELONGS HERE:**
- Typer command functions with decorators
- CLI-specific argument parsing (`--week-ending`, `-p`)
- Rich output formatting calls
- Exit code handling

**MUST NOT BELONG HERE:**
- Business logic (delegate to app/commands)
- Direct database access
- Direct registry/framework calls

#### `cli/interactive/`

**BELONGS HERE:**
- Questionary-based interactive prompts
- Menu navigation
- User input collection

**MUST NOT BELONG HERE:**
- Business logic
- Direct command execution (should shell out or call commands)

#### `cli/console.py`, `cli/ui.py`

**BELONGS HERE:**
- Rich console singleton
- Panel/table rendering helpers
- CLI-specific formatting

**CURRENT VIOLATION:**
- `console.py` has `TIER_VALUES`, `TIER_ALIASES`, `normalize_tier()` — duplicates domain logic

#### `cli/params.py`

**BELONGS HERE:**
- CLI-specific parameter parsing (`--param key=value`)
- Source merging for CLI inputs

**CURRENT VIOLATION:**
- Calls `normalize_tier()` from `console.py` — should delegate to services

---

### `tests/`

**BELONGS HERE:**
- Unit tests for commands, services
- Integration tests for API (TestClient)
- Parity tests (CLI/API consistency)
- Registry and error handling tests

**MUST NOT BELONG HERE:**
- Production code
- Test fixtures that duplicate domain logic

---

## External Packages

### `spine-core` (`packages/spine-core/`)

**BELONGS HERE:**
- Framework code: Dispatcher, Runner, Registry
- Pipeline base classes
- Logging infrastructure
- Schema utilities (idempotency, manifest, quality)

**MUST NOT BELONG HERE:**
- FINRA/OTC-specific constants
- Tier values or aliases
- Domain table names

### `spine-domains` (`packages/spine-domains/`)

**BELONGS HERE:**
- FINRA OTC Transparency schema (Tier enum, TIER_VALUES, TIER_ALIASES)
- Pipeline implementations (@register_pipeline)
- Domain-specific calculations, normalizers, connectors

**CURRENT STATE:**
- ✅ TIER_VALUES, TIER_ALIASES defined here (single source of truth)
- ✅ Pipeline classes registered here
- ✅ Domain constants properly encapsulated
