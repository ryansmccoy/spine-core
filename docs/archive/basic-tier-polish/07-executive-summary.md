# Executive Summary — API & Architecture Refactor Review

> **Purpose**: Consolidated findings, key corrections, and prioritized action items for the Market Spine Basic tier API and architecture refactor.

---

## Overall Assessment

The proposed architecture is **directionally sound** but has **three key corrections** needed:

| Area | Proposal | Correction |
|------|----------|------------|
| **Service location** | Move services to `spine-core.services` | Move to `market_spine.app.services` |
| **Command abstraction** | Generic `Command[I, O]` base class | Start with concrete classes, no ABC |
| **API evolution** | "Contracts stable across tiers" | Acknowledge sync→async is behavioral change |

The architecture documents are thorough and well-reasoned. The main risk is **over-engineering for Basic tier** — adding abstractions (command registries, DI containers, middleware) that aren't yet needed.

---

## Key Findings by Section

### 1. Package Ownership

**Verdict:** Good model, wrong locations.

| Issue | Impact | Fix |
|-------|--------|-----|
| Proposed `spine-core.services` | Pollutes framework with tier logic | Use `market_spine.app.services` |
| Tier constants in CLI | Can't be reused by API | Move to `spine.domains.finra.constants` |
| Connection init scattered | Every CLI file calls `init_connection_provider()` | Call once at application startup |

### 2. CLI → API Boundary

**Verdict:** Boundary is clear, extraction plan is solid.

| Issue | Impact | Fix |
|-------|--------|-----|
| 277-line `run.py` does everything | Can't reuse logic | Extract to `RunPipelineCommand` |
| Exceptions used for flow control | API can't return structured errors | Commands return `Result` with `error` field |
| `normalize_tier()` in console.py | CLI-only location | Extract to `TierNormalizer` service |

### 3. Shared Command Architecture

**Verdict:** Pattern is correct, implementation is over-engineered.

| Issue | Impact | Fix |
|-------|--------|-----|
| Generic `Command[TInput, TOutput]` | Adds no value in Basic | Use concrete classes |
| Constructor DI for services | Ceremony without benefit | Instantiate services directly |
| Missing error handling pattern | Commands can't fail gracefully | Add `CommandError` and `Result` base |

### 4. API Surface — Basic

**Verdict:** Good endpoint selection, minor refinements needed.

| Issue | Impact | Fix |
|-------|--------|-----|
| `/v1/query/weeks` naming | "Query" is verb, not resource | Rename to `/v1/data/weeks` |
| `POST /v1/pipelines/{name}/resolve` | Redundant with dry_run | Remove, use dry_run instead |
| No `FEATURE_NOT_SUPPORTED` error | Unknown features silently ignored | Add explicit error code |

### 5. Evolution Roadmap

**Verdict:** Underestimates friction, needs guardrails.

| Issue | Impact | Fix |
|-------|--------|-----|
| "Contracts stable across tiers" | Sync→async changes response shape | Document `status: pending` in v1 |
| No capability endpoint | Clients can't discover tier features | Add `GET /v1/capabilities` |
| No forward-compatible schema | Migrations are harder | Add nullable future columns now |

### 6. API Vision & Philosophy

**Verdict:** Philosophy is sound, needs formalization.

| Issue | Impact | Fix |
|-------|--------|-----|
| No versioning policy | Unclear what's breaking | Define breaking change criteria |
| No error code registry | Inconsistent error handling | Establish code enum |
| CLI concepts in API | `--explain-source` became API field | Separate CLI affordances from API |

---

## Do Now / Defer / Never Do

### ✅ Do Now (Before API Implementation)

| # | Action | Owner | Effort |
|---|--------|-------|--------|
| 1 | Move tier constants to `spine.domains.finra.constants` | Domain | S |
| 2 | Create `market_spine/app/services/` with `TierNormalizer`, `ParameterResolver`, `IngestResolver` | Basic | M |
| 3 | Create `market_spine/app/commands/` with `ListPipelinesCommand`, `RunPipelineCommand` | Basic | M |
| 4 | Define `CommandError` and `Result` base classes | Basic | S |
| 5 | Consolidate `init_connection_provider()` to single call at startup | Basic | S |
| 6 | Add `/v1/capabilities` endpoint returning tier and features | API | S |
| 7 | Add `/v1/health` endpoint (simplest, validates stack) | API | S |
| 8 | Write unit tests for extracted services and commands | Basic | M |

### ⏸️ Defer (Until Needed)

| # | Action | Trigger |
|---|--------|---------|
| 9 | Generic `Command` ABC | If polymorphism needed across commands |
| 10 | Dependency injection framework | If testing requires complex mocking |
| 11 | Command middleware (logging, auth) | When building Advanced tier |
| 12 | `/v1/verify/*` endpoints | If there's consumer demand |
| 13 | `/v1/executions/{id}` GET | When Intermediate adds persistence |
| 14 | Pagination for list endpoints | When data volume grows |
| 15 | Migration tooling (Basic → Intermediate) | When Intermediate is ready |

### ❌ Never Do

| # | Action | Why Not |
|---|--------|---------|
| 16 | Put tier logic in `spine-core` | Framework must be tier-agnostic |
| 17 | Create command registry | Just import classes directly |
| 18 | Create command bus | Adds indirection without value |
| 19 | Expose `/v1/db/*` endpoints | Admin ops are dangerous via API |
| 20 | Add GraphQL | REST is sufficient, GraphQL adds complexity |
| 21 | Add WebSocket in Basic | Sync execution doesn't need it |
| 22 | Reference CLI flags in API docs | API is independent |
| 23 | Return lane/worker_id in responses | Internal implementation details |
| 24 | Feature flags for tier selection | Use separate packages instead |

---

## Implementation Roadmap

### Week 1: Services Extraction

```
market_spine/app/
├── __init__.py
├── services/
│   ├── __init__.py
│   ├── tier.py         # TierNormalizer
│   ├── params.py       # ParameterResolver
│   └── ingest.py       # IngestResolver
└── models.py           # CommandError, Result
```

- Extract `normalize_tier()` → `TierNormalizer`
- Extract `ParamParser.merge_params()` → `ParameterResolver`
- Extract ingest resolution logic → `IngestResolver`
- CLI still works, now imports from `app.services`

### Week 2: Commands Extraction

```
market_spine/app/commands/
├── __init__.py
├── pipelines.py        # ListPipelinesCommand, DescribePipelineCommand
├── executions.py       # RunPipelineCommand
└── queries.py          # QueryWeeksCommand, QuerySymbolsCommand
```

- Create command classes with `execute(request) -> result`
- Refactor CLI commands to be thin wrappers
- All existing CLI tests must pass

### Week 3: API Foundation

```
market_spine/api/
├── __init__.py
├── main.py             # FastAPI app
├── routes/
│   ├── __init__.py
│   ├── health.py       # /v1/health
│   ├── capabilities.py # /v1/capabilities
│   └── pipelines.py    # /v1/pipelines
└── models.py           # Pydantic response models
```

- Add FastAPI dependency
- Implement `/v1/health` and `/v1/capabilities`
- Implement `/v1/pipelines` (read-only)
- Add `spine api` CLI command to start server

### Week 4: Full API

```
market_spine/api/routes/
├── executions.py       # /v1/executions
└── data.py             # /v1/data/weeks, /v1/data/symbols
```

- Implement `/v1/executions` (POST)
- Implement `/v1/data/*` (GET)
- Write API integration tests
- Generate and validate OpenAPI spec

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Over-extraction slows delivery | Medium | Medium | Extract only high-value commands first |
| API breaks CLI | Low | High | CLI tests gate all changes |
| Sync→async transition breaks clients | Medium | High | Document `status: pending` in v1 schema |
| Scope creep adds unused endpoints | Medium | Low | Gate additions on consumer demand |
| Auth retrofitting is awkward | Medium | Medium | Design headers now, enforce in Advanced |

---

## Success Criteria

The refactor is successful when:

1. ✅ **CLI behavior unchanged** — All existing CLI tests pass
2. ✅ **Commands are reusable** — Same command works for CLI and API
3. ✅ **Services are testable** — Unit tests cover `TierNormalizer`, etc.
4. ✅ **API is self-documenting** — OpenAPI spec is generated, accurate
5. ✅ **No `spine-core` pollution** — Tier logic stays in `market-spine-basic`
6. ✅ **Upgrade path is clear** — `/v1/capabilities` shows tier features

---

## Conclusion

The proposed architecture is solid. The main adjustments are:

1. **Location correction**: Services go in `market_spine.app`, not `spine-core`
2. **Simplification**: Skip ABC/generics for Basic tier
3. **Explicit evolution**: Add capability introspection and reserved fields

Start with services extraction (Week 1), then commands (Week 2), then API (Weeks 3-4). The CLI remains the source of truth until API is validated.
