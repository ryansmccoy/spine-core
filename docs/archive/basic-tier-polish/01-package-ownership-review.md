# Package Ownership — Architecture Review

> **Review Focus**: Validate the proposed package ownership model, identify logic misplacement, and propose clean ownership contracts.

---

## SWOT Validation

### Strengths — Confirmed ✅

The analysis correctly identifies:

1. **Clear conceptual split exists** — `spine-core` (framework), `spine-domains` (business logic), `market-spine-basic` (product) is a sound architecture.

2. **CLI isolation prevents coupling** — Keeping CLI in `market-spine-basic` was the right call. The CLI doesn't pollute the framework.

3. **Domain structure backs APIs cleanly** — The FINRA OTC pipelines in `spine-domains` are self-contained and registry-driven. They're already API-ready.

### Strengths — Challenged 🔶

**"Domains could back APIs cleanly"** — True, but with a gap. The domain pipelines return `PipelineResult` objects, which are framework-level. The proposed API needs richer response shapes (ingest resolution details, parameter schemas). This gap must be filled by the command layer, not by enriching domain code.

---

### Weaknesses — Confirmed ✅

1. **Business intent lives in CLI layer** — Reading `console.py` and `params.py` confirms this. Tier normalization (`normalize_tier`) and parameter merging (`ParamParser.merge_params`) are currently CLI-only but contain reusable business logic.

2. **CLI becoming de facto API** — The CLI's `run.py` already does orchestration (dispatcher calls, ingest resolution). If someone wanted programmatic access today, they'd import CLI modules—a red flag.

### Weaknesses — Missing from Analysis ⚠️

3. **Database initialization scattered** — `init_connection_provider()` is called at the top of every CLI command file. This should be handled once at application startup, not per-module.

4. **Tier constants duplicated** — `TIER_VALUES` and `TIER_ALIASES` live in `console.py`. These are domain knowledge, not CLI presentation. They should live in `spine-domains` or `spine-core`.

---

### Opportunities — Validated ✅

1. **Extract service layer** — Yes, but the proposed location is wrong (see below).

2. **Ownership rules to prevent drift** — Critical. The current codebase has no enforcement mechanism.

### Opportunities — Refined

The proposal suggests:
> "Move non-UX logic into `spine-core.services`"

**This is architecturally wrong.** Here's why:

- `spine-core` is **tier-agnostic**. It doesn't know about SQLite, Postgres, or specific tier behaviors.
- Parameter resolution (e.g., deriving `file_path` from `week_ending` and `tier`) is **tier-specific** logic because file paths vary by deployment.
- Tier normalization (`tier1 → NMS_TIER_1`) is **domain-specific**, not framework-level.

**Correct locations:**

| Logic | Current Location | Proposed | Correct Location |
|-------|------------------|----------|------------------|
| Tier normalization | `market_spine.cli.console` | `spine-core.services` | `spine.domains.finra` (domain knowledge) |
| Parameter merging | `market_spine.cli.params` | `spine-core.services` | `market_spine.app.services` (tier-specific) |
| Ingest path derivation | `market_spine.cli.commands.run` | `spine-core.services` | `market_spine.app.services` (tier-specific) |
| Dispatcher | `spine.framework.dispatcher` | (keep) | ✅ Already correct |

---

### Threats — Confirmed ✅

1. **Over-extracting too early** — Real risk. Creating a command layer with 20 files when 3 would suffice is premature.

2. **API logic duplicated across tiers** — If `market-spine-intermediate` reimplements parameter resolution, drift is inevitable.

### Threats — Additional

3. **Import cycles** — If `spine-core` tries to import from `spine-domains` for tier constants, you'll hit circular imports. The current `spine.framework.db` injection pattern avoids this; tier logic must follow the same pattern.

4. **Testing gaps** — No unit tests exist for the CLI-embedded business logic. Extraction will require writing these tests first.

---

## Flawed Assumptions

### 1. "Move orchestration rules into spine-core"

**Flaw**: Conflates "framework" with "application services."

The framework (`spine-core`) provides:
- Pipeline registration (`@register_pipeline`)
- Execution dispatch (`Dispatcher.submit`)
- Logging and observability primitives

The framework does **not** provide:
- Tier normalization (that's domain knowledge)
- Parameter precedence rules (that's application policy)
- File path derivation (that's tier-specific)

**Fix**: Create `market_spine.app.services` as the home for this logic. This keeps `spine-core` clean while allowing CLI and API to share behavior.

---

### 2. "spine-core: orchestration, validation, service APIs"

**Flaw**: Too broad. If validation means "is this tier value correct?", that's domain logic. If it means "are required params present?", that's already in `PipelineSpec.validate()`.

The proposal's categorization:
> spine-core: execution, validation, orchestration, **service APIs**

The term "service APIs" is ambiguous. Does it mean:
- HTTP APIs? (No—those belong in tier packages)
- Internal service interfaces? (Partially—only framework-level ones)

**Fix**: Tighten the definition:
- **spine-core**: Execution engine, logging, registry, pipeline interface
- **spine-domains**: Business logic, calculations, normalizers, domain validation
- **market-spine-***: Storage, presentation, application services, configuration

---

### 3. "market-spine-basic: UX only"

**Flaw**: This undersells the tier package's responsibility.

`market-spine-basic` is not "just UX." It is a complete product that:
- Configures the database (SQLite)
- Wires dependencies (connection provider)
- Implements application services (command layer)
- Provides interfaces (CLI, API)

**Fix**: Rename the categorization:
- **market-spine-basic**: Complete product (storage, services, interfaces)

---

## Concrete Ownership Contract

### spine-core Owns:

```
spine.framework.
├── dispatcher.py     # Execution coordination
├── runner.py         # Synchronous execution
├── registry.py       # Pipeline discovery
├── params.py         # PipelineSpec, ParamDef (schema definition)
├── pipelines/        # Pipeline, PipelineResult base classes
├── db.py             # Connection protocol + injection hook
├── logging/          # Structured logging
└── exceptions.py     # PipelineNotFoundError, BadParamsError
```

**Rules**:
- Zero imports from `spine.domains` or `market_spine`
- No SQLite, Postgres, or storage-specific code
- No tier constants or domain vocabulary

---

### spine-domains Owns:

```
spine.domains.
├── finra/
│   ├── otc_transparency/
│   │   ├── pipelines.py    # Registered pipelines
│   │   ├── normalizers.py  # Record transformation
│   │   ├── calculations.py # Volume, price aggregations
│   │   ├── constants.py    # TIERS enum, STAGES, TABLES
│   │   └── connectors.py   # File parsing (not storage)
```

**Rules**:
- May import from `spine.framework`
- Uses `get_connection()` for DB access (injected by tier)
- No CLI/API code, no presentation logic
- Exports domain constants (e.g., `Tier` enum) that tiers can use

---

### market-spine-basic Owns:

```
market_spine/
├── config.py               # Settings (paths, env vars)
├── db.py                   # SQLite connection, migrations
├── app/                    # Application services layer (NEW)
│   ├── commands/           # Use-case implementations
│   │   ├── pipelines.py    # ListPipelines, DescribePipeline
│   │   ├── executions.py   # RunPipeline, GetExecution
│   │   └── queries.py      # QueryWeeks, QuerySymbols
│   ├── services/           # Shared logic
│   │   ├── tier.py         # TierNormalizer (imports from domains)
│   │   ├── params.py       # ParameterResolver
│   │   └── ingest.py       # IngestResolver (file path derivation)
│   └── models.py           # Request/Response dataclasses
├── cli/                    # CLI adapter
│   ├── commands/           # Typer commands (thin wrappers)
│   └── ui.py               # Rich formatting
└── api/                    # API adapter (future)
    ├── routes/             # FastAPI routers
    └── models.py           # Pydantic response models
```

**Rules**:
- Owns database configuration and migrations
- Owns application services (command layer)
- CLI and API are thin adapters calling `app/commands`
- May import from `spine.framework` and `spine.domains`

---

## Decision Tree: Where Does This Code Go?

```
Is it framework infrastructure?
├── Yes → spine-core
│   Examples: Dispatcher, Registry, Pipeline base class
│
└── No → Is it business/domain logic?
    ├── Yes → spine-domains
    │   Examples: FINRA normalizers, tier enum, calculations
    │
    └── No → Is it tier-specific?
        ├── Yes → market-spine-{tier}
        │   Examples: SQLite connection, file path derivation, CLI
        │
        └── No → Probably doesn't belong anywhere. Question the need.
```

---

## Recommendations

### Do Now ✅

1. **Move `TIER_VALUES` and `TIER_ALIASES`** from `market_spine.cli.console` to `spine.domains.finra.otc_transparency.constants`
   - Update imports in CLI
   - Add `Tier` enum if not already present

2. **Create `market_spine.app.services.tier.TierNormalizer`**
   - Imports tier constants from domains
   - Provides `normalize()` method
   - CLI and API both use this

3. **Consolidate connection initialization**
   - Call `init_connection_provider()` once in `market_spine/__init__.py` or entry point
   - Remove per-file calls

### Defer ⏸️

4. **Full command layer extraction** — Wait until API work begins. The current CLI works; don't refactor for refactoring's sake.

5. **Abstract base classes for commands** — Start with simple functions or classes. ABC + generics can come later if needed.

### Never Do ❌

6. **Put tier normalization in `spine-core`** — This is domain knowledge, not framework.

7. **Create a `spine-api` package** — The API is tier-specific. Each tier has its own needs (sync vs async, auth, etc.).

8. **Import `market_spine` from `spine-core` or `spine-domains`** — This would invert the dependency graph and break the architecture.

---

## Summary

The proposed ownership model is **directionally correct** but **imprecise in boundaries**. The key correction is:

> `spine-core.services` should be `market_spine.app.services`

Framework code must remain tier-agnostic. Application services—the glue between CLI/API and the framework—belong in the tier package.
