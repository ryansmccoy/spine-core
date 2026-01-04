# Basic → Intermediate → Advanced: API Layering Plan (Reusable Across Tiers)

## Goal
Add an HTTP API to **Basic tier** that can:
- list pipelines and params
- run pipelines (sync in Basic)
- query data (weeks, symbols, etc.)
…and evolve naturally into Intermediate/Advanced without rewriting everything.

Key requirement: **do not duplicate logic** between CLI and API.

---

## Architecture: “Command Layer” as the shared core
Create an application layer that both the CLI and API call.

### Recommended layering
1. **Domain + framework** (already exists)
   - pipelines, dispatcher, runner
   - domain code in `spine-domains`
2. **Command / use-case layer (NEW)**
   - pure functions/classes that implement:
     - “list pipelines”
     - “run pipeline”
     - “query weeks”
     - “query symbols”
     - “verify tables/data”
   - returns **typed results** (Pydantic models or dataclasses)
3. **Adapters**
   - CLI adapter (Typer): parses args → calls command layer → renders Rich UI
   - API adapter (FastAPI later): parses JSON/query params → calls command layer → returns JSON

This keeps behavior identical across CLI and API while allowing different UX.

---

## Basic-tier API surface (minimal, useful, stable)
Use a versioned prefix from day 1: `/v1/...`

### Pipelines
- `GET /v1/pipelines`
  - returns: name, description, params schema (optional summary)
- `GET /v1/pipelines/{name}`
  - returns: full param schema + examples
- `POST /v1/pipelines/{name}/dry-run`
  - validates + returns resolved params (no execution)

### Executions (sync in Basic, async later)
- `POST /v1/executions`
  - body: `{ pipeline: str, params: dict, lane?: str, dry_run?: bool }`
  - Basic: runs synchronously by default, returns `{ execution_id, status, metrics, duration_ms }`
  - Intermediate+: returns immediately with status `submitted` and a polling URL

- `GET /v1/executions/{execution_id}`
  - returns status + metrics + timestamps

### Query
- `GET /v1/query/weeks`
- `GET /v1/query/symbols?week=YYYY-MM-DD&tier=...&top=10`
- optional: `GET /v1/query/symbol/{symbol}?week=...&tier=...`

### Verify / Health
- `GET /v1/verify/tables`
- `GET /v1/verify/data`
- `GET /v1/doctor` (environment + DB connectivity + schema present)

---

## Keeping CLI and API consistent
### Use the same parameter schema / validation
- The pipeline registry already knows params (required/optional, types).
- Expose that schema to both:
  - CLI: `--help-params` and option generation
  - API: OpenAPI schema for requests

### Tier normalization
- Put tier normalization in the command layer:
  - accept aliases (`Tier1`) but emit canonical (`NMS_TIER_1`) in responses

### Execution semantics across tiers
- Basic: sync execution, SQLite
- Intermediate: Postgres/Timescale, async workers
- Advanced: multi-tenant, auth, rate limits, caching
**API contract stays stable**; only execution mode changes.

---

## Suggested folder structure (Basic tier)
*(Exact paths can vary; this is one clean option.)*

```
market_spine/
  app/
    models.py          # Pydantic response/request models
    commands/
      pipelines.py     # list pipelines, params help
      executions.py    # run pipeline, dry-run, execution status
      queries.py       # weeks, symbols, symbol detail
      verify.py        # tables/data verification
      doctor.py
    services/
      tier.py          # tier normalization + aliases
      params.py        # shared param parsing/validation (CLI + API)
  cli/                 # thin adapter → calls app.commands.*
  api/                 # thin adapter → calls app.commands.* (later)
```

---

## Implementation plan (Basic)
1. **Create the command layer** (no HTTP yet)
   - Move query/verify/run logic out of CLI commands into `app/commands/*`
   - Ensure the CLI uses only the command layer

2. **Add a minimal FastAPI app**
   - `uv run spine api` starts a local server
   - Implement `/v1/pipelines`, `/v1/executions`, `/v1/query/*`, `/v1/verify/*`

3. **Tests**
   - Unit tests for command layer (pure functions)
   - A few API tests using FastAPI TestClient
   - Keep integration tests in `market-spine-basic` unchanged

---

## Claude Implementation Prompt (copy/paste)
Design and implement an HTTP API for Basic tier that reuses the same behavior as the CLI.

**Requirements**
- Add a shared “command layer” (use-case layer) that both CLI and API call.
- Implement a minimal FastAPI server with `/v1` endpoints:
  - pipelines: list + describe
  - executions: submit/run + status
  - query: weeks + symbols
  - verify: tables + data
  - doctor: health check
- Sync execution is fine in Basic tier, but structure code so it can become async later.
- Tier normalization must match DB values (`OTC`, `NMS_TIER_1`, `NMS_TIER_2`) and accept aliases.
- Avoid duplication: CLI must call command layer; API must call the same command layer.

**Deliverables**
- New `market_spine/app/` package with command modules + Pydantic models
- New `market_spine/api/` package with FastAPI app
- `spine api` command to run the server locally
- Tests for command layer + a few API endpoint tests
- Updated README docs: CLI + API examples

**Acceptance**
- `uv run spine api` runs and serves OpenAPI docs
- `GET /v1/pipelines` shows the FINRA OTC pipelines
- `POST /v1/executions` can run `normalize_week` and return metrics
- `GET /v1/query/weeks` returns aggregated weeks
