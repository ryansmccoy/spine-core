# API Vision & Philosophy — Architecture Review

> **Review Focus**: Articulate a clear API philosophy. Define what the API is NOT responsible for. Recommend principles that should guide all future API changes.

---

## SWOT Validation

### Strengths — Confirmed ✅

1. **CLI already expresses user intent well** — Commands like `spine run`, `spine query`, `spine verify` are clear action verbs with clear subjects.

2. **Strong mental model around pipelines and time** — The domain is well-understood: pipelines process data for a given week/tier.

3. **Phase-based execution aligns with observability** — `PipelineResult` includes metrics, status, and timing—all observable.

### Strengths — Challenged 🔶

**"Phase-based execution aligns with observability"** — True for the framework, but the current API design doesn't expose phases. An execution returns a final result, not intermediate progress. For long-running pipelines, this is limiting.

**Mitigation:** For Basic tier, this is acceptable (sync execution). Intermediate should add `/v1/executions/{id}/progress` or similar.

---

### Weaknesses — Confirmed ✅

1. **Vision not yet formalized** — The existing `API_VISION.md` document is thorough but hasn't been ratified as policy. It's a proposal, not a standard.

2. **Risk of CLI dictating API shape** — Confirmed. The `--explain-source` flag became `ingest_resolution` in API responses. CLI-specific affordances are leaking.

3. **Ambiguous audience** — Is the API for:
   - Humans writing scripts? (Friendly errors, readable field names)
   - Machines in CI/CD? (Stable contracts, machine-parseable)
   - Both? (Tension between friendliness and stability)

### Weaknesses — Additional ⚠️

4. **No versioning policy** — The docs mention `/v1/` paths but don't define:
   - When does v2 happen?
   - What constitutes a breaking change?
   - How long is v1 supported?

5. **No error contract** — Error responses have codes and messages, but:
   - Is the list of codes exhaustive?
   - Can new codes be added without breaking clients?
   - Should clients parse `details` or treat it as opaque?

---

### Opportunities — Validated ✅

1. **Treat API as programmable Spine** — Yes. The API makes Spine automatable.

2. **Enable research automation, dashboards, agents** — Yes. These are real use cases.

3. **Expose orchestration metadata** — Partially. Current design exposes execution results, not orchestration internals (lanes, queues).

### Opportunities — Refined

**"Eventually expose orchestration metadata"** — Be cautious. Internal implementation details (lanes, worker IDs) shouldn't be API surface. Expose *what happened*, not *how*.

```json
// Good: What happened
{"status": "completed", "duration_seconds": 2.5}

// Bad: How (internal detail)
{"lane": "backfill", "worker_id": "worker-3", "queue_position": 5}
```

---

### Threats — Confirmed ✅

1. **Designing API for everything** — Risk of scope creep. Every CLI feature wants an API equivalent.

2. **Mixing UX concepts into API** — Confirmed. "Help params" is a CLI UX concept, not an API operation.

3. **Forgetting that APIs live longer than CLIs** — True. CLI can change defaults and add flags. API changes are breaking.

### Threats — Identified

4. **Overspecification** — The existing docs are very detailed. This is good for clarity but locks in decisions early.

5. **Underestimating versioning costs** — Running v1 and v2 simultaneously is expensive. Avoid the need for v2 by designing v1 carefully.

---

## API Philosophy (Revised)

### Statement

> **The Market Spine API is a stable, typed interface for running and querying pipelines.**
> 
> - It is **not** a CLI wrapper.
> - It is **not** a database explorer.
> - It is **not** an admin console.
>
> It enables **automation, integration, and observability** for programmatic consumers.

### The API Is For:

| Consumer | Use Case | Example |
|----------|----------|---------|
| Scripts | Automate pipeline runs | Cron job: `POST /v1/executions` |
| Dashboards | Display status | React app: `GET /v1/health` |
| Notebooks | Interactive analysis | Jupyter: `GET /v1/data/symbols` |
| CI/CD | Validate data processing | GitHub Action: `POST /v1/executions` with dry_run |
| Monitoring | Health checks | Prometheus: `GET /v1/health` |

### The API Is NOT For:

| Anti-Use Case | Why Not | Alternative |
|---------------|---------|-------------|
| Database administration | Dangerous, no auth | Use CLI: `spine db reset` |
| Schema exploration | Changes frequently | Read source code or docs |
| Interactive help | Not a REPL | Read OpenAPI docs |
| Log streaming (Basic) | Sync execution | Wait for Intermediate |
| Bulk data export | Not optimized for this | Direct DB access |

---

## Core Principles

### 1. Resources Over Actions

Model the API around **resources**, not CLI commands.

**Bad:**
```
POST /v1/run-pipeline
POST /v1/list-pipelines
POST /v1/describe-pipeline
```

**Good:**
```
POST /v1/executions        (create an execution)
GET  /v1/pipelines         (list pipelines)
GET  /v1/pipelines/{name}  (get a pipeline)
```

Pipelines are a resource. Executions are a resource. Actions operate on resources.

### 2. Explicit Over Implicit

The API should be **more explicit** than the CLI.

| CLI (Implicit) | API (Explicit) |
|----------------|----------------|
| Tier aliases (`tier1`) | Returns canonical tier (`NMS_TIER_1`) |
| Derived file paths | Returns `ingest_resolution` explaining derivation |
| Exit codes for errors | Returns structured error with code, message, details |
| Progress bars | Returns `status` and metrics |

### 3. Additive Evolution

Changes should be **additive**, not breaking.

**Allowed:**
- Add new optional field to response
- Add new endpoint
- Add new error code
- Add new query parameter (optional)

**Not Allowed:**
- Remove field from response
- Rename field
- Change field type
- Remove endpoint
- Change required parameter to optional (or vice versa)

### 4. Errors Are Part of the Contract

Error responses are **first-class API outputs**, not exceptional cases.

**Define explicitly:**
- Error codes are enumerated (new codes can be added)
- Error messages are human-readable (can change)
- Error details are structured (schema is stable)

**Client guidance:**
- Parse `error.code` for programmatic handling
- Display `error.message` for humans
- Log `error.details` for debugging

### 5. Introspection Over Documentation

The API should be **self-describing**.

- OpenAPI spec generated from code (always accurate)
- Response models include all fields (reserved fields are null)
- `/v1/capabilities` endpoint describes tier features

Don't rely on external documentation being read. Embed information in the API.

### 6. Stability Over Features

When in doubt, **don't add it**.

Every new endpoint is a maintenance burden. Every new field is a compatibility constraint. Prefer a smaller, stable API over a feature-rich, volatile one.

**Add features when:**
- Multiple consumers have requested it
- It's clearly aligned with API purpose
- It can be added without breaking changes

### 7. One Way to Do Things

Avoid multiple ways to achieve the same outcome.

**Bad:**
```
POST /v1/executions {"pipeline": "foo", ...}
POST /v1/pipelines/foo/run
POST /v1/run {"pipeline": "foo"}
```

**Good:**
```
POST /v1/executions {"pipeline": "foo", ...}
```

One endpoint for running pipelines. Period.

---

## What the API Is NOT Responsible For

### 1. Authentication (Basic Tier)

**Responsibility:** None. API is local-only.

**Implication:** Document that Basic is single-user. Don't add auth headers "just in case."

**Future:** Advanced tier owns auth. The endpoint paths don't change; headers become required.

### 2. User Interface Affordances

**Responsibility:** None. The API is not interactive.

**These stay CLI-only:**
- `--help-params` (show parameter help)
- `--quiet` (suppress output)
- Interactive mode (menu prompts)
- Pretty-printed tables

### 3. Administrative Operations

**Responsibility:** None. Admin ops are CLI-only.

**These stay CLI-only:**
- `spine db init`
- `spine db reset`
- Migration execution
- Log level configuration

### 4. Data Export

**Responsibility:** Limited. Query endpoints return samples, not full datasets.

**What API provides:**
- `GET /v1/data/weeks` — List available weeks
- `GET /v1/data/symbols?top=10` — Top 10 symbols

**What API does NOT provide:**
- Full table dumps
- Arbitrary SQL execution
- CSV/Parquet export

For bulk data, consumers should access the database directly.

### 5. Real-Time Updates (Basic Tier)

**Responsibility:** None in Basic. All operations are synchronous.

**What API provides:**
- Request/response HTTP

**What API does NOT provide (until Intermediate):**
- WebSocket connections
- Server-Sent Events
- Polling endpoints for long-running tasks

---

## Versioning Policy

### Version Numbering

```
/v1/pipelines
/v2/pipelines  (when breaking changes are unavoidable)
```

### Breaking Change Definition

A **breaking change** is anything that could cause a working client to fail:

| Change Type | Breaking? |
|-------------|-----------|
| Remove endpoint | ✅ Yes |
| Remove response field | ✅ Yes |
| Rename response field | ✅ Yes |
| Change field type | ✅ Yes |
| Add required request parameter | ✅ Yes |
| Add optional request parameter | ❌ No |
| Add response field | ❌ No |
| Add new endpoint | ❌ No |
| Add new error code | ❌ No |
| Change error message text | ❌ No |

### Version Lifecycle

1. **v1 Active** — Current version, fully supported
2. **v1 Deprecated** — Still works, logs warnings, docs marked deprecated
3. **v1 Sunset** — Removed after deprecation period (minimum 6 months)

### Avoiding v2

The goal is to **never need v2**. Strategies:

1. **Reserved fields** — Add nullable fields for future features
2. **Additive changes only** — New endpoints, new optional fields
3. **Capability negotiation** — Clients query capabilities, not version

If v2 becomes necessary, run v1 and v2 in parallel during transition.

---

## Error Contract

### Structure

```json
{
  "error": {
    "code": "PIPELINE_NOT_FOUND",
    "message": "Pipeline 'foo.bar' not found in registry.",
    "details": {
      "requested_pipeline": "foo.bar",
      "suggestion": "Did you mean 'finra.otc_transparency.ingest_week'?"
    }
  }
}
```

### Field Definitions

| Field | Type | Stability | Client Usage |
|-------|------|-----------|--------------|
| `code` | string enum | Stable, additive | Switch on code for handling |
| `message` | string | Can change | Display to users |
| `details` | object | Schema stable per code | Log for debugging |

### Error Code Registry

| Code | HTTP Status | Meaning |
|------|-------------|---------|
| `PIPELINE_NOT_FOUND` | 404 | Pipeline name not registered |
| `INVALID_PARAMS` | 400 | Params failed validation |
| `INVALID_TIER` | 400 | Tier value not recognized |
| `EXECUTION_FAILED` | 500 | Pipeline threw exception |
| `DATABASE_ERROR` | 500 | Database operation failed |
| `FEATURE_NOT_SUPPORTED` | 400 | Feature not available in this tier |
| `NOT_IMPLEMENTED` | 501 | Endpoint reserved for future |

New codes may be added. Clients should handle unknown codes gracefully.

---

## Recommendations

### Do Now ✅

1. **Adopt the philosophy statement** — "Stable, typed interface for running and querying pipelines"

2. **Define breaking change policy** — Document what is/isn't breaking

3. **Establish error code registry** — Start with 7 codes above

4. **Add `/v1/capabilities` endpoint** — Tier and feature introspection

5. **Remove implicit behaviors** — Always return canonical tier values, always return ingest_resolution for ingest pipelines

### Defer ⏸️

6. **Versioning policy enforcement** — No v2 planned yet

7. **Detailed error details schemas** — Define per-code schemas when codes are used

8. **API changelog** — Start when API goes public

### Never Do ❌

9. **Reference CLI flags in API docs** — API is independent

10. **Add "convenience" endpoints** — One way to do things

11. **Return internal implementation details** — Hide lanes, workers, queues

12. **Design for hypothetical consumers** — Build for known use cases

---

## Summary

The API philosophy can be summarized as:

> **Do one thing well: provide stable access to pipeline execution and data queries.**

Key principles:
1. Resources over actions
2. Explicit over implicit
3. Additive evolution only
4. Errors are first-class
5. Introspection over documentation
6. Stability over features
7. One way to do things

The API is NOT responsible for: authentication (Basic), UI affordances, admin ops, bulk export, or real-time updates (Basic).
