# Evolution Roadmap

> **Purpose**: Show how the API architecture scales across tiers, what changes at each stage, and what remains stable.

---

## Tier Progression Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              EVOLUTION TRAJECTORY                                        │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   BASIC              INTERMEDIATE           ADVANCED              FULL                  │
│   ─────              ────────────           ────────              ────                  │
│                                                                                          │
│   SQLite             Postgres               Postgres              Postgres + replicas   │
│   Sync               Async + Workers        Async + Scheduling    Async + Auto-scaling  │
│   Single-user        Multi-user (no auth)   Auth + RBAC           Multi-tenant          │
│   Local              Dockerized             Kubernetes            Cloud-native          │
│                                                                                          │
│   ────────────────────────────────────────────────────────────────────────────────────  │
│                                                                                          │
│                     STABLE ACROSS ALL TIERS                                             │
│                     ───────────────────────                                             │
│                                                                                          │
│   • API contracts (endpoints, request/response shapes)                                  │
│   • Command layer interface                                                             │
│   • Pipeline registry and execution model                                               │
│   • Domain logic (calculations, normalizers)                                            │
│   • Parameter validation                                                                │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Basic Tier (Current)

### Characteristics

| Aspect | Implementation |
|--------|----------------|
| **Database** | SQLite (single file) |
| **Execution** | Synchronous (blocking) |
| **API** | HTTP, sync handlers |
| **CLI** | Full-featured, immediate results |
| **Auth** | None (local use) |
| **Deployment** | Single process |
| **Users** | Single user |

### API Behavior

```
POST /v1/executions
{
  "pipeline": "finra.otc_transparency.normalize_week",
  "params": { "week_ending": "2025-12-19", "tier": "NMS_TIER_1" }
}

─── waits synchronously ───

200 OK
{
  "execution_id": "exec_abc123",
  "status": "completed",
  "duration_ms": 5234,
  "metrics": { ... }
}
```

### What Works

- ✅ Full pipeline execution
- ✅ All query capabilities
- ✅ Health checks and verification
- ✅ OpenAPI documentation
- ✅ CLI and API consistency

### Limitations

- ❌ Long-running pipelines block requests
- ❌ No concurrent execution
- ❌ Single database file
- ❌ No access control
- ❌ No execution history persistence

---

## Intermediate Tier

### What Changes

| Aspect | Basic → Intermediate |
|--------|----------------------|
| **Database** | SQLite → Postgres/TimescaleDB |
| **Execution** | Sync → Async (job queue) |
| **Workers** | None → Background workers |
| **Execution tracking** | In-memory → Persisted table |
| **Scaling** | Single process → Multiple workers |

### API Behavior Changes

```
POST /v1/executions
{
  "pipeline": "finra.otc_transparency.backfill_range",
  "params": { "start_date": "2025-01-01", "end_date": "2025-12-31" }
}

─── returns immediately ───

202 Accepted
{
  "execution_id": "exec_abc123",
  "status": "submitted",
  "poll_url": "/v1/executions/exec_abc123"
}

─── client polls ───

GET /v1/executions/exec_abc123

200 OK
{
  "execution_id": "exec_abc123",
  "status": "running",
  "progress": { "completed": 15, "total": 52 }
}

─── later ───

200 OK
{
  "execution_id": "exec_abc123",
  "status": "completed",
  "duration_ms": 325000,
  "metrics": { "weeks_processed": 52 }
}
```

### New Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /v1/executions` | List recent executions |
| `DELETE /v1/executions/{id}` | Cancel a running execution |
| `GET /v1/executions/{id}/logs` | Stream execution logs (SSE) |

### New Response Fields

```json
{
  "execution_id": "exec_abc123",
  "status": "running",
  "progress": {
    "current_step": "normalize_week",
    "completed": 15,
    "total": 52,
    "percent": 28.8
  },
  "worker_id": "worker-02",
  "queue": "default"
}
```

### What Does NOT Change

- ✅ Endpoint paths (`/v1/pipelines`, `/v1/executions`, etc.)
- ✅ Request body structure
- ✅ Response model fields (new fields are additive)
- ✅ Error codes and formats
- ✅ Query endpoints
- ✅ Health check structure

### Implementation Approach

```python
# market_spine_intermediate/app/commands/executions.py

class RunPipelineCommand:
    """Same interface, different implementation."""
    
    def execute(self, request: RunPipelineRequest) -> RunPipelineResult:
        # Validate parameters (same as Basic)
        resolved = self.param_resolver.resolve(request.params)
        if not resolved.is_valid:
            return RunPipelineResult(
                success=False,
                error=resolved.validation_errors[0],
            )
        
        # Different from Basic: submit to queue instead of running
        job = self.job_queue.submit(
            pipeline=request.pipeline,
            params=resolved.params,
            lane=request.lane,
        )
        
        # Return immediately with pending status
        return RunPipelineResult(
            success=True,
            execution_id=job.execution_id,
            status="submitted",
            poll_url=f"/v1/executions/{job.execution_id}",
        )
```

---

## Advanced Tier

### What Changes

| Aspect | Intermediate → Advanced |
|--------|-------------------------|
| **Authentication** | None → API keys / OAuth |
| **Authorization** | None → RBAC (roles, permissions) |
| **Multi-user** | Single context → User-scoped |
| **Audit** | Basic logging → Full audit trail |
| **Scheduling** | None → Cron-like schedules |
| **Rate limiting** | None → Per-user/key limits |

### New Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /v1/auth/token` | Exchange credentials for token |
| `GET /v1/users/me` | Get current user info |
| `GET /v1/schedules` | List scheduled executions |
| `POST /v1/schedules` | Create a schedule |
| `GET /v1/audit/events` | Query audit trail |

### Request Changes (Auth Headers)

```
POST /v1/executions
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
X-Request-ID: req_abc123

{
  "pipeline": "finra.otc_transparency.normalize_week",
  "params": { ... }
}
```

### Response Changes (Ownership)

```json
{
  "execution_id": "exec_abc123",
  "status": "completed",
  "owner": {
    "user_id": "user_xyz789",
    "username": "analyst@company.com"
  },
  "created_by": "user_xyz789",
  "team": "data-engineering"
}
```

### Schedule Endpoint

```
POST /v1/schedules
{
  "pipeline": "finra.otc_transparency.backfill_range",
  "params": { "tier": "NMS_TIER_1" },
  "schedule": {
    "type": "cron",
    "expression": "0 6 * * MON",
    "timezone": "America/New_York"
  },
  "name": "Weekly NMS Tier 1 Refresh"
}

201 Created
{
  "schedule_id": "sched_def456",
  "name": "Weekly NMS Tier 1 Refresh",
  "next_run": "2026-01-06T06:00:00-05:00",
  "status": "active"
}
```

### What Does NOT Change

- ✅ Core endpoint paths
- ✅ Pipeline execution semantics
- ✅ Query capabilities
- ✅ Error codes (new codes are additive)
- ✅ Health check structure

### New Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `UNAUTHORIZED` | 401 | Missing or invalid auth |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `RATE_LIMITED` | 429 | Too many requests |
| `QUOTA_EXCEEDED` | 402 | Execution quota reached |

---

## Full Tier

### What Changes

| Aspect | Advanced → Full |
|--------|-----------------|
| **Multi-tenant** | Single-tenant → Isolated tenants |
| **Data isolation** | Shared tables → Per-tenant schemas |
| **Billing** | None → Usage-based |
| **External integrations** | None → Webhooks, S3, etc. |
| **High availability** | Single region → Multi-region |

### New Concepts

#### Tenant Context

```
POST /v1/executions
Authorization: Bearer ...
X-Tenant-ID: tenant_acme

{
  "pipeline": "finra.otc_transparency.normalize_week",
  "params": { ... }
}
```

#### Webhooks

```
POST /v1/webhooks
{
  "url": "https://company.com/api/spine-callback",
  "events": ["execution.completed", "execution.failed"],
  "secret": "..."
}
```

#### External Data Sources

```json
{
  "pipeline": "finra.otc_transparency.ingest_week",
  "params": {
    "file_source": {
      "type": "s3",
      "bucket": "finra-data",
      "key": "weekly/otc_2025-12-19.psv"
    }
  }
}
```

### What Does NOT Change

- ✅ API contract structure
- ✅ Pipeline execution model
- ✅ Command layer interface

---

## Change Summary by Tier

### Additive Changes

| Change Type | Basic | Intermediate | Advanced | Full |
|-------------|-------|--------------|----------|------|
| Core endpoints | ✅ | ✅ | ✅ | ✅ |
| Async execution | ❌ | ✅ | ✅ | ✅ |
| Progress tracking | ❌ | ✅ | ✅ | ✅ |
| Execution history | ❌ | ✅ | ✅ | ✅ |
| Auth headers | ❌ | ❌ | ✅ | ✅ |
| RBAC | ❌ | ❌ | ✅ | ✅ |
| Scheduling | ❌ | ❌ | ✅ | ✅ |
| Audit trail | ❌ | ❌ | ✅ | ✅ |
| Tenant context | ❌ | ❌ | ❌ | ✅ |
| Webhooks | ❌ | ❌ | ❌ | ✅ |
| External sources | ❌ | ❌ | ❌ | ✅ |

### Breaking Changes: NONE

The architecture is designed so that **no breaking changes are required** between tiers:

1. **New fields are additive** — Old clients ignore them
2. **New endpoints are additive** — Old clients don't call them
3. **New headers are optional** — Old requests still work
4. **Execution semantics are transparent** — Sync vs async is hidden behind same contract

### Client Compatibility

A client written for Basic tier should work unchanged on:
- Intermediate: Same requests, may need to poll for results
- Advanced: Same requests, may need auth headers
- Full: Same requests, may need tenant headers

```python
# Basic client
response = client.post("/v1/executions", json={
    "pipeline": "finra.otc_transparency.normalize_week",
    "params": {"week_ending": "2025-12-19", "tier": "NMS_TIER_1"}
})

# Works on all tiers
# - Basic: Returns completed result
# - Intermediate+: May return 202, client polls poll_url if present
```

---

## Migration Paths

### Basic → Intermediate

1. **Database migration**: SQLite → Postgres
   - Export data from SQLite
   - Run Postgres migrations
   - Import data to Postgres

2. **Code changes**:
   - Swap `db.py` for Postgres provider
   - Add job queue configuration
   - Deploy workers

3. **API changes**: None required (additive only)

### Intermediate → Advanced

1. **Infrastructure**: Add auth provider (Keycloak, Auth0, etc.)

2. **Code changes**:
   - Add auth middleware
   - Add RBAC checks
   - Add audit logging

3. **API changes**: Clients need to add auth headers

### Advanced → Full

1. **Database**: Add tenant isolation (schemas or databases)

2. **Infrastructure**: Multi-region, billing system

3. **Code changes**:
   - Tenant routing middleware
   - Usage metering

4. **API changes**: Clients need tenant headers

---

## Invariants Across All Tiers

These aspects NEVER change:

### 1. Pipeline Interface

```python
class Pipeline(ABC):
    name: str
    description: str
    spec: PipelineSpec | None
    
    @abstractmethod
    def run(self) -> PipelineResult:
        ...
```

### 2. Parameter Validation

```python
spec.validate(params) → ValidationResult
```

### 3. Registry

```python
list_pipelines() → list[str]
get_pipeline(name) → type[Pipeline]
```

### 4. Execution Model

```python
dispatcher.submit(pipeline, params) → Execution
```

### 5. API Contract (v1)

```
GET  /v1/pipelines
GET  /v1/pipelines/{name}
POST /v1/executions
GET  /v1/executions/{id}
GET  /v1/query/weeks
GET  /v1/query/symbols
GET  /v1/health
```

### 6. Error Format

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": { ... }
  }
}
```

---

## Risk Mitigation

### Risk: Premature Optimization

**Mitigation**: Start with simplest implementation (Basic), extract patterns only when needed.

### Risk: API Drift

**Mitigation**: Command layer ensures CLI and API call same code. Tests verify consistency.

### Risk: Breaking Changes

**Mitigation**: Version prefix (`/v1/`) from day one. New features are additive.

### Risk: Over-Engineering

**Mitigation**: Each tier is a complete, usable product. No "placeholder" code.

---

## Timeline Recommendation

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 1** | 1-2 weeks | Command layer extraction |
| **Phase 2** | 1-2 weeks | Basic API with FastAPI |
| **Phase 3** | — | Ship Basic, gather feedback |
| **Phase 4** | 2-3 weeks | Intermediate (Postgres + async) |
| **Phase 5** | — | Ship Intermediate, gather feedback |
| **Phase 6** | 3-4 weeks | Advanced (auth + scheduling) |
| **Phase 7** | — | Assess need for Full tier |

**Key principle**: Each phase produces a shippable, valuable product. No long cycles before value delivery.
