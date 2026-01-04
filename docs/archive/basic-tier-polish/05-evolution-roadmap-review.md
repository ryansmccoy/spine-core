# Evolution Roadmap — Architecture Review

> **Review Focus**: Identify assumptions that may cause friction in evolving from Basic to Advanced tiers. Suggest guardrails to keep Basic simple while not blocking future tiers.

---

## SWOT Validation

### Strengths — Confirmed ✅

1. **Clear tiered vision exists** — The four tiers (Basic, Intermediate, Advanced, Full) are well-defined with distinct capabilities.

2. **Data model is forward-looking** — The domain pipelines use `PipelineResult` and `PipelineStatus` that work for both sync and async execution.

3. **Tests give confidence** — The CLI test suite (`test_cli_comprehensive.ps1`) validates behavior. This enables safe refactoring.

### Strengths — Challenged 🔶

**"Data model is forward-looking"** — Partially true. The `Execution` dataclass in `dispatcher.py` is designed for evolution:

```python
@dataclass
class Execution:
    id: str
    pipeline: str
    params: dict[str, Any]
    lane: Lane
    trigger_source: TriggerSource
    status: PipelineStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    result: PipelineResult | None
```

However, this is **in-memory only** in Basic. Intermediate needs database persistence, which means:
- Schema migration for `executions` table
- Changed retrieval patterns (query by ID, not in-memory lookup)

The interface is forward-looking; the implementation is not.

---

### Weaknesses — Confirmed ✅

1. **Risk of locking early decisions** — The existing documents specify API endpoint shapes, error codes, and response formats. Changing these later is breaking.

2. **Tier boundaries may blur** — If Basic implements "just one more feature" (like execution history), the line between Basic and Intermediate erodes.

3. **API evolution could diverge from CLI** — If API gets features CLI doesn't have (or vice versa), mental model diverges.

### Weaknesses — Identified ⚠️

4. **No feature flags or capability queries** — There's no API endpoint to ask "what tier is this?" or "is async execution supported?". Clients can't adapt to capabilities.

5. **Sync-to-async transition is hard** — Basic returns results inline. Intermediate returns job IDs and requires polling. This is a behavioral change, not just a new field.

6. **Auth is retrofitted** — Adding authentication to an API that was designed without it often leads to awkward patterns (optional headers, public endpoints, etc.).

---

### Opportunities — Validated ✅

1. **Versioned APIs per tier** — Yes, but versioning should be by API version (`/v1/`, `/v2/`), not by tier. A v1 endpoint should work the same across tiers.

2. **Gradual extraction of execution engine** — Yes. The `Dispatcher` is already designed to be replaceable.

3. **Reuse same domain logic everywhere** — Yes. Domain pipelines are tier-agnostic.

### Opportunities — Refined

**"Versioned APIs per tier"** — This is the wrong model. The correct model is:

```
/v1/executions — Tier-agnostic endpoint
  Basic:        Sync execution, returns result
  Intermediate: Async execution, returns job ID + poll URL
  Advanced:     Same + auth context in request
```

Behavior changes, but the endpoint path doesn't. Add `Tier-Capability` headers or a `/v1/capabilities` endpoint for introspection.

---

### Threats — Confirmed ✅

1. **"Basic hacks" leaking upward** — Risk confirmed. If Basic adds `--force` flags or shortcuts, higher tiers inherit them.

2. **CLI features driving architecture** — Risk confirmed. The CLI's `--explain-source` became an API design point. CLI affordances shouldn't dictate API shape.

3. **Inconsistent behavior across tiers** — Risk confirmed. If Basic's `POST /v1/executions` returns `{"status": "completed"}` but Intermediate returns `{"status": "pending"}`, clients break.

### Threats — Identified

4. **Migration complexity** — Upgrading from Basic to Intermediate requires:
   - Database migration (SQLite → Postgres)
   - Execution table schema
   - Worker infrastructure
   - Config changes
   
   There's no migration tooling or guide.

5. **Backward compatibility pressure** — Once Basic's API is public, Intermediate must maintain compatibility. This limits design freedom.

---

## Friction Points by Tier Transition

### Basic → Intermediate

| Change | Friction | Mitigation |
|--------|----------|------------|
| SQLite → Postgres | Schema migration | Provide migration scripts |
| Sync → Async | API behavior change | Return `status: pending` with poll URL |
| In-memory executions → Persistent | New table | Design schema now, don't implement |
| No workers → Workers | Infrastructure | Document worker setup |

**Key Assumption to Validate:**
> "API contracts remain stable across tiers"

This is **partially false**. The response for `POST /v1/executions` changes:

```json
// Basic
{"status": "completed", "execution_id": "exec_123", "metrics": {...}}

// Intermediate
{"status": "pending", "execution_id": "exec_123", "poll_url": "/v1/executions/exec_123"}
```

**Mitigation:** Document that `status: pending` is a valid response. Basic never returns it, but clients should handle it.

### Intermediate → Advanced

| Change | Friction | Mitigation |
|--------|----------|------------|
| No auth → Auth required | Breaking for existing clients | Use optional headers in design |
| Single-user → Multi-user | Resource ownership | Add `owner` fields now (nullable) |
| No scheduling → Scheduled runs | New endpoints | Reserve `/v1/schedules` path |
| No rate limiting → Rate limits | `429` responses | Document rate limit headers |

**Key Assumption to Validate:**
> "Auth can be added later"

This is **optimistic**. Adding auth to an existing API is awkward:
- Do unauthenticated clients still work?
- Are there public endpoints?
- How do existing scripts migrate?

**Mitigation:** Design with auth in mind. All endpoints accept (but don't require) `Authorization` header in Basic. Document that auth is optional now, required in Advanced.

### Advanced → Full

| Change | Friction | Mitigation |
|--------|----------|------------|
| Single-tenant → Multi-tenant | Schema changes | Use tenant_id column from start |
| Single region → Multi-region | Infra complexity | Out of scope for API design |
| No billing → Usage-based | New domain | Out of scope for Basic |

**Key Assumption to Validate:**
> "Multi-tenancy can be layered on"

This is **hard**. Multi-tenancy affects:
- Database schema (tenant_id on every table)
- API routing (tenant context in every request)
- Data isolation (queries filtered by tenant)

**Mitigation:** Add `tenant_id` column to schema now as nullable. Don't enforce it until Full tier.

---

## Guardrails for Basic Tier

### 1. Explicit "Not Supported" Responses

When Basic receives a request for a feature it doesn't support:

```json
POST /v1/executions
{"async": true, ...}

→ 400 Bad Request
{
  "error": {
    "code": "FEATURE_NOT_SUPPORTED",
    "message": "Async execution is not supported in Basic tier. All executions are synchronous.",
    "supported_in": "Intermediate"
  }
}
```

Don't silently ignore unknown fields. Fail explicitly.

### 2. Capability Endpoint

```
GET /v1/capabilities
```

```json
{
  "tier": "basic",
  "version": "0.1.0",
  "capabilities": {
    "sync_execution": true,
    "async_execution": false,
    "execution_history": false,
    "authentication": false,
    "scheduling": false,
    "rate_limiting": false
  }
}
```

Clients can query capabilities and adapt.

### 3. Reserved Fields

Include fields in response models that Basic doesn't populate:

```json
// POST /v1/executions response
{
  "execution_id": "exec_123",
  "status": "completed",
  "poll_url": null,        // Reserved for Intermediate
  "owner": null,           // Reserved for Advanced
  "tenant_id": null        // Reserved for Full
}
```

This establishes the schema early. Higher tiers fill in the values.

### 4. Schema Forward-Compatibility

Design database schema with future columns:

```sql
-- Basic tier schema
CREATE TABLE executions (
    id TEXT PRIMARY KEY,
    pipeline TEXT NOT NULL,
    params JSON NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    error TEXT,
    metrics JSON,
    -- Reserved for higher tiers (nullable)
    owner_id TEXT,
    tenant_id TEXT,
    scheduled_at TEXT,
    worker_id TEXT
);
```

Basic ignores these columns. Intermediate/Advanced use them.

### 5. Deprecation Strategy

When Basic behavior must change:

1. Add new field/endpoint without removing old
2. Mark old as deprecated in OpenAPI
3. Log warnings when deprecated feature used
4. Remove in next major version

Example:
```yaml
# OpenAPI
/v1/executions:
  post:
    requestBody:
      properties:
        lane:
          type: string
          deprecated: true
          description: "Deprecated in v1.1. Ignored in Basic tier."
```

---

## Upgrade Triggers

Document when to move to the next tier:

### Basic → Intermediate

Move when you need:
- [ ] Background execution (pipelines >30 seconds)
- [ ] Execution history (query past runs)
- [ ] Concurrent writes (>1 writer at a time)
- [ ] PostgreSQL features (better JSON, concurrency)

### Intermediate → Advanced

Move when you need:
- [ ] Multi-user access
- [ ] API authentication
- [ ] Scheduled/recurring runs
- [ ] Audit trail
- [ ] Rate limiting

### Advanced → Full

Move when you need:
- [ ] Multi-tenant isolation
- [ ] Usage-based billing
- [ ] Geographic distribution
- [ ] External integrations (webhooks, S3)

---

## Anti-Patterns to Avoid

### 1. "Just Add a Flag"

**Bad:**
```python
# In Basic tier code
if config.ENABLE_ASYNC:  # "We'll just turn this on later"
    return async_execute(...)
else:
    return sync_execute(...)
```

**Why Bad:** Feature flags accumulate. Code becomes unreadable. Tests don't cover flag combinations.

**Better:** Different tiers have different `Dispatcher` implementations.

### 2. "We'll Fix It in Intermediate"

**Bad:** "This edge case is annoying, but we'll handle it properly in Intermediate."

**Why Bad:** Technical debt compounds. Intermediate inherits Basic's problems.

**Better:** Fix it now or document it as a known limitation.

### 3. "Same Code, Different Config"

**Bad:**
```python
# One codebase, tier selected by env var
if os.environ["TIER"] == "basic":
    DB_URL = "sqlite:///data.db"
else:
    DB_URL = os.environ["POSTGRES_URL"]
```

**Why Bad:** All tiers' code is deployed everywhere. Attack surface increases.

**Better:** Separate packages with shared dependencies:
- `spine-core` (shared)
- `spine-domains` (shared)
- `market-spine-basic` (Basic-only)
- `market-spine-intermediate` (Intermediate-only)

### 4. "Optional Everything"

**Bad:**
```python
def run_pipeline(
    pipeline: str,
    params: dict,
    async_: bool = False,  # Optional for Basic
    auth_token: str | None = None,  # Optional for Basic
    tenant_id: str | None = None,  # Optional for Basic
    schedule: str | None = None,  # Optional for Basic
    priority: int = 0,  # Optional for Basic
):
```

**Why Bad:** Function signature becomes unwieldy. Every tier must handle every parameter.

**Better:** Tier-specific request models:
```python
# Basic
@dataclass
class RunPipelineRequest:
    pipeline: str
    params: dict
    dry_run: bool = False

# Intermediate (extends Basic)
@dataclass
class RunPipelineRequestAsync(RunPipelineRequest):
    async_: bool = True

# Advanced (extends Intermediate)
@dataclass
class RunPipelineRequestAuth(RunPipelineRequestAsync):
    auth_context: AuthContext | None = None
```

---

## Recommendations

### Do Now ✅

1. **Add `/v1/capabilities` endpoint** — Returns tier and supported features

2. **Include reserved nullable fields** in response models:
   - `poll_url`, `owner`, `tenant_id`

3. **Design schema with future columns** — Add nullable columns for higher tiers

4. **Document upgrade triggers** — Clear checklist for "when to move to Intermediate"

5. **Fail explicitly on unsupported features** — Return `FEATURE_NOT_SUPPORTED` error

### Defer ⏸️

6. **Migration tooling** — Build when Intermediate is ready

7. **Auth header parsing** — Accept header but don't validate until Advanced

8. **Deprecation warnings** — Add when there's something to deprecate

### Never Do ❌

9. **Feature flags for tier selection** — Use separate packages

10. **Silent ignoring of unknown fields** — Fail explicitly

11. **"We'll fix it later" debt** — Fix now or document as limitation

12. **Shared codebase for all tiers** — Separate tier-specific code

---

## Summary

The evolution roadmap is **sound in direction** but **underestimates friction**:

| Transition | Friction Level | Key Mitigation |
|------------|----------------|----------------|
| Basic → Intermediate | High | Schema forward-compatibility, async response handling |
| Intermediate → Advanced | Medium | Auth header design, ownership fields |
| Advanced → Full | High | Tenant isolation is architectural |

The main risk is **assuming API contracts are stable** when behavioral changes (sync → async) are significant. Mitigate by:

1. Designing response models with reserved fields
2. Adding capability introspection
3. Documenting upgrade triggers explicitly
4. Failing loudly on unsupported features
