# API Surface — Basic Tier — Architecture Review

> **Review Focus**: Propose a Basic-tier API surface. Decide which CLI commands map to API endpoints and which remain CLI-only. Justify exclusions.

---

## SWOT Validation

### Strengths — Confirmed ✅

1. **API can mirror CLI mental model** — The CLI's command structure (`spine pipelines list`, `spine run run`, `spine query weeks`) maps naturally to REST resources (`/pipelines`, `/executions`, `/query/weeks`).

2. **SQLite acceptable for local API** — For single-user, local-first usage, SQLite handles concurrent reads fine. Writes are serialized, which is acceptable for Basic.

3. **Clear upgrade path** — The existing `API_SURFACE_BASIC.md` document defines endpoints that work for both sync (Basic) and async (Intermediate) execution models.

### Strengths — Challenged 🔶

**"API can mirror CLI mental model"** — Partially true, but some CLI concepts don't translate:

| CLI Concept | API Translation |
|-------------|-----------------|
| `--dry-run` | `"dry_run": true` in body ✅ |
| `--help-params` | ❌ No API equivalent (use OpenAPI docs) |
| `--explain-source` | Return `ingest_resolution` always, not on request |
| Interactive prompts | ❌ Not applicable |

---

### Weaknesses — Confirmed ✅

1. **Risk of exposing internals too early** — The current design exposes `Execution` objects with internal details (`lane`, `trigger_source`). Consider if API clients need these.

2. **Authentication unnecessary in Basic** — Correct. But the API should still set `Authorization` header to `N/A` or document that it's local-only.

3. **Hard to decide what not to expose** — This is the core challenge. Every CLI command *could* be an API endpoint, but shouldn't be.

### Weaknesses — Additional ⚠️

4. **`/v1/` versioning assumed but not enforced** — There's no mechanism to block unversioned routes. FastAPI allows `/pipelines` and `/v1/pipelines` to coexist accidentally.

5. **Query endpoints mix concerns** — `GET /v1/query/weeks` and `GET /v1/query/symbols` are under a generic `/query` namespace. Better to model as `/v1/data/weeks` or reconsider the resource model.

---

### Opportunities — Validated ✅

1. **"Headless CLI" via API** — Yes. Scripts that currently shell out to `spine run ...` could use HTTP instead.

2. **Enable notebooks and dashboards** — Yes. Jupyter notebooks can call the API for execution; dashboards can poll health.

3. **Encourage testability via HTTP** — Yes. Integration tests can hit the API instead of importing Python modules.

### Opportunities — Expanded

4. **OpenAPI-first documentation** — FastAPI generates OpenAPI from route definitions. This becomes the source of truth.

5. **Simpler error handling** — HTTP status codes are universal. No need to parse CLI exit codes or Rich output.

---

### Threats — Confirmed ✅

1. **Overexposing domain internals** — The proposed `execution` response includes `lane` and `trigger_source`. These are framework internals. Clients don't need to know execution was CLI-triggered.

2. **Locking API shape too early** — Once the API is documented, changes are breaking. Version carefully.

3. **Mixing orchestration and querying** — The same API exposes both "do things" (`POST /executions`) and "ask things" (`GET /query/weeks`). This is fine, but be deliberate about it.

### Threats — Identified

4. **SQLite concurrent write issues** — If two API requests try to run pipelines simultaneously, SQLite's write lock could cause contention. Basic should document "single concurrent write" limitation.

---

## CLI to API Mapping

### Direct Mappings (Include in API)

| CLI Command | HTTP Endpoint | Method | Notes |
|-------------|---------------|--------|-------|
| `spine pipelines list` | `/v1/pipelines` | GET | Filter via query param |
| `spine pipelines describe {name}` | `/v1/pipelines/{name}` | GET | Full details |
| `spine run run {pipeline} ...` | `/v1/executions` | POST | Submit execution |
| `spine query weeks` | `/v1/data/weeks` | GET | Renamed from `/query/weeks` |
| `spine query symbols` | `/v1/data/symbols` | GET | Renamed from `/query/symbols` |
| `spine doctor doctor` | `/v1/health` | GET | System health |

### Partial Mappings (Modified for API)

| CLI Feature | API Handling |
|-------------|--------------|
| `--dry-run` | `"dry_run": true` in POST body |
| `--explain-source` | Always return `ingest_resolution` in response |
| `--lane` | Accept but ignore in Basic (document as "reserved for future") |
| Tier aliases (`tier1`, `OTC`) | Accept and normalize server-side; return canonical value |

### Exclusions (CLI-Only)

| CLI Feature | Why Excluded |
|-------------|--------------|
| `--help-params` | Interactive help. Use OpenAPI docs. |
| `--quiet` | Controls terminal output. Irrelevant for JSON. |
| `spine pipelines describe` examples section | CLI-specific examples. OpenAPI has examples. |
| Interactive mode (`spine run --interactive`) | By definition, not API-compatible. |
| `spine db init`, `spine db reset` | Administrative. Dangerous via API. |
| `spine verify table`, `spine verify data` | Lower priority. Add in v1.1 if needed. |

---

## Revised Endpoint Specifications

### Pipeline Discovery

#### List Pipelines

```
GET /v1/pipelines?prefix=finra.otc
```

**Response 200:**
```json
{
  "pipelines": [
    {
      "name": "finra.otc_transparency.ingest_week",
      "description": "Ingest FINRA OTC transparency data for a week"
    }
  ],
  "count": 1
}
```

**Notes:**
- Simple list, no pagination (Basic has few pipelines)
- Add pagination in Intermediate if list grows

#### Describe Pipeline

```
GET /v1/pipelines/finra.otc_transparency.ingest_week
```

**Response 200:**
```json
{
  "name": "finra.otc_transparency.ingest_week",
  "description": "Ingest FINRA OTC transparency data for a week",
  "parameters": {
    "required": {
      "week_ending": {
        "type": "string",
        "description": "Week ending date (YYYY-MM-DD)"
      },
      "tier": {
        "type": "string",
        "description": "Market tier",
        "enum": ["OTC", "NMS_TIER_1", "NMS_TIER_2"]
      }
    },
    "optional": {
      "file_path": {
        "type": "string",
        "description": "Explicit file path (overrides derivation)"
      }
    }
  },
  "is_ingest": true
}
```

**Notes:**
- `parameters` structure matches OpenAPI schema format
- `is_ingest` helps clients understand file path behavior

---

### Pipeline Execution

#### Run Pipeline

```
POST /v1/executions
Content-Type: application/json

{
  "pipeline": "finra.otc_transparency.normalize_week",
  "params": {
    "week_ending": "2025-12-19",
    "tier": "NMS_TIER_1"
  },
  "dry_run": false
}
```

**Response 200 (Success):**
```json
{
  "execution_id": "exec_7f3a9b2c",
  "status": "completed",
  "duration_seconds": 2.45,
  "metrics": {
    "rows_processed": 15234,
    "capture_id": "20251219_nms1"
  },
  "ingest_resolution": null
}
```

**Response 200 (Dry Run):**
```json
{
  "execution_id": null,
  "status": "dry_run",
  "duration_seconds": null,
  "metrics": null,
  "ingest_resolution": {
    "source_type": "derived",
    "file_path": "data/finra/finra_otc_weekly_nms_tier_1_2025-12-19.csv",
    "derivation_logic": "Pattern: data/finra/finra_otc_weekly_{tier}_{week}.csv"
  },
  "would_execute": {
    "pipeline": "finra.otc_transparency.normalize_week",
    "params": {
      "week_ending": "2025-12-19",
      "tier": "NMS_TIER_1"
    }
  }
}
```

**Response 400 (Validation Error):**
```json
{
  "error": {
    "code": "INVALID_PARAMS",
    "message": "Parameter validation failed",
    "details": {
      "missing": ["tier"],
      "invalid": []
    }
  }
}
```

**Response 404 (Pipeline Not Found):**
```json
{
  "error": {
    "code": "PIPELINE_NOT_FOUND",
    "message": "Pipeline 'foo.bar' not found"
  }
}
```

**Response 500 (Execution Failed):**
```json
{
  "execution_id": "exec_7f3a9b2c",
  "status": "failed",
  "duration_seconds": 1.23,
  "error": {
    "code": "EXECUTION_FAILED",
    "message": "Database error: table not found"
  }
}
```

**Design Decisions:**

1. **`execution_id` is nullable for dry run** — Dry runs don't create executions.

2. **`ingest_resolution` always returned for ingest pipelines** — Don't require `explain_source=true`.

3. **Errors in response body, not just HTTP status** — Clients can distinguish `INVALID_PARAMS` from `EXECUTION_FAILED`.

---

### Data Queries

#### Query Weeks

```
GET /v1/data/weeks?tier=NMS_TIER_1&limit=10
```

**Response 200:**
```json
{
  "tier": "NMS_TIER_1",
  "weeks": [
    {"week_ending": "2025-12-19", "symbol_count": 4523},
    {"week_ending": "2025-12-12", "symbol_count": 4498}
  ],
  "count": 2,
  "limit": 10
}
```

**Response 400 (Invalid Tier):**
```json
{
  "error": {
    "code": "INVALID_TIER",
    "message": "Invalid tier: 'FOO'. Valid values: OTC, NMS_TIER_1, NMS_TIER_2"
  }
}
```

#### Query Symbols

```
GET /v1/data/symbols?tier=NMS_TIER_1&week=2025-12-19&top=10
```

**Response 200:**
```json
{
  "tier": "NMS_TIER_1",
  "week": "2025-12-19",
  "symbols": [
    {"symbol": "AAPL", "volume": 125000000, "avg_price": 178.45},
    {"symbol": "MSFT", "volume": 98000000, "avg_price": 425.30}
  ],
  "count": 2,
  "top": 10
}
```

---

### Health Check

```
GET /v1/health
```

**Response 200 (Healthy):**
```json
{
  "status": "healthy",
  "checks": {
    "database": {"status": "ok", "message": "Connected"},
    "tables": {"status": "ok", "message": "All tables present"},
    "pipelines": {"status": "ok", "message": "5 pipelines registered"}
  },
  "version": "0.1.0"
}
```

**Response 503 (Unhealthy):**
```json
{
  "status": "unhealthy",
  "checks": {
    "database": {"status": "error", "message": "Connection failed"},
    "tables": {"status": "unknown"},
    "pipelines": {"status": "ok", "message": "5 pipelines registered"}
  },
  "version": "0.1.0"
}
```

---

## What NOT to Include (with Justification)

### 1. `/v1/db/init`, `/v1/db/reset`

**CLI:** `spine db init`, `spine db reset --force`

**Why Exclude:**
- Database initialization is administrative, not operational
- Accidental API call could destroy data
- No authentication in Basic means no way to protect this

**Alternative:** Document that database setup is CLI-only.

### 2. `/v1/verify/*`

**CLI:** `spine verify table {name}`, `spine verify data`

**Why Exclude:**
- Low API demand (mostly CLI debugging)
- Can be added in v1.1 if requested
- Health check covers basic "is the system working?" needs

**Alternative:** Fold basic checks into `/v1/health`.

### 3. `/v1/executions/{id}`

**CLI:** No equivalent (execution details are printed inline)

**Why Exclude in Basic:**
- Basic tier has no execution persistence. Executions are in-memory.
- Once the request completes, the execution is gone.
- Intermediate tier will add this with database-backed execution log.

**Note:** The endpoint path is reserved. Basic returns `501 Not Implemented`.

### 4. `/v1/pipelines/{name}/resolve`

**Proposed in existing docs as:**
```
POST /v1/pipelines/{name}/resolve
{"params": {"week_ending": "2025-12-19", "tier": "OTC"}}
```

**Why Exclude:**
- Redundant. `POST /v1/executions` with `"dry_run": true` already returns resolution.
- Adding a separate endpoint fragments the API surface.

**Alternative:** Use `dry_run` mode of `/v1/executions`.

### 5. `DELETE /v1/executions/{id}`

**Purpose:** Cancel running execution

**Why Exclude:**
- Basic tier is synchronous. Executions can't be cancelled—they're blocking.
- Intermediate tier with background workers will need this.

---

## Error Code Catalog

| Code | HTTP Status | When |
|------|-------------|------|
| `PIPELINE_NOT_FOUND` | 404 | Pipeline name not in registry |
| `INVALID_PARAMS` | 400 | Missing required or invalid params |
| `INVALID_TIER` | 400 | Tier value not recognized |
| `EXECUTION_FAILED` | 500 | Pipeline raised an exception |
| `DATABASE_ERROR` | 500 | SQLite error |
| `NOT_IMPLEMENTED` | 501 | Endpoint reserved for higher tier |

---

## Framework Choice: FastAPI

### Why FastAPI

| Criterion | FastAPI | Flask | Verdict |
|-----------|---------|-------|---------|
| OpenAPI generation | Automatic from type hints | Manual or via extensions | **FastAPI** |
| Async support | Native | Via `async-flask` | **FastAPI** (future-proof) |
| Pydantic integration | Built-in | Manual | **FastAPI** |
| Learning curve | Moderate | Low | Flask slightly easier |
| Dependency injection | Built-in | Manual | **FastAPI** |

### FastAPI Recommendation

Use FastAPI for:
1. **Auto-generated OpenAPI docs** — Crucial for API discoverability
2. **Pydantic validation** — Request/response models with automatic validation
3. **Async readiness** — Intermediate tier will use `async def`

### Basic Tier: Sync Handlers

```python
# Basic tier uses sync handlers (no async needed for SQLite)
@router.post("/v1/executions")
def run_pipeline(body: RunPipelineBody) -> RunPipelineResponse:
    # Synchronous execution
    result = RunPipelineCommand().execute(...)
    return RunPipelineResponse(...)
```

### Intermediate Tier: Async Handlers

```python
# Intermediate tier adds async for Postgres + background tasks
@router.post("/v1/executions")
async def run_pipeline(body: RunPipelineBody) -> RunPipelineResponse:
    # Submit to background worker
    task_id = await task_queue.submit(...)
    return RunPipelineResponse(execution_id=task_id, status="pending")
```

---

## Recommendations

### Do Now ✅

1. **Define Pydantic models** for request/response bodies
   - `RunPipelineBody`, `RunPipelineResponse`
   - `PipelineListResponse`, `PipelineDetailResponse`
   - `ErrorResponse` with code/message/details

2. **Create `/v1/` prefix in route definitions**
   ```python
   router = APIRouter(prefix="/v1")
   ```

3. **Implement `/v1/health` first** — Simplest endpoint, validates the stack

4. **Implement `/v1/pipelines` and `/v1/pipelines/{name}`** — Read-only, low risk

5. **Implement `/v1/executions` last** — Most complex, depends on command layer

### Defer ⏸️

6. **`/v1/verify/*`** — Add in v1.1 if there's demand

7. **`/v1/executions/{id}` GET** — Wait for Intermediate tier persistence

8. **Pagination** — Basic has few pipelines and weeks; add when data grows

9. **CORS configuration** — Only needed when web clients exist

### Never Do ❌

10. **`/v1/db/*` endpoints** — Database admin is CLI-only

11. **`/run?help_params=true`** — This is a CLI affordance, not API

12. **GraphQL** — REST is sufficient; GraphQL adds complexity

13. **WebSocket in Basic** — Polling is fine for sync execution

---

## Summary

The Basic tier API should be **minimal and focused**:

| Include | Exclude |
|---------|---------|
| List/describe pipelines | DB init/reset |
| Run pipelines (sync) | Execution cancellation |
| Query weeks/symbols | Verify endpoints |
| Health check | Execution history |

The API surface is a **proper subset** of CLI capabilities. CLI-only features (interactive mode, help-params, quiet mode) don't translate to API and shouldn't try to.

FastAPI is the right framework choice for OpenAPI generation and async-readiness.
