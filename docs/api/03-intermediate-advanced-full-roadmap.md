# API Evolution Roadmap

> Last Updated: 2026-01-04  
> Version: 1.0  
> Status: **AUTHORITATIVE**

This document maps the API evolution from Basic through Full tier, showing what changes, what stays stable, and what gets deprecated at each stage.

---

## 1. Evolution Principles

### Additive Changes Only (Within Major Version)

Each tier **adds** to the previous tier's API surface:

```
Basic → Intermediate → Advanced → Full
  ↓          ↓            ↓         ↓
 Core      + Async     + DLQ     + Multi-tenant
           + History   + Retry   + Streaming
           + Auth      + Events  + Caching
```

### Stability Guarantees

| Guarantee | Scope |
|-----------|-------|
| **Endpoints don't disappear** | Within v1, no endpoint removal |
| **Fields don't disappear** | Response fields stable |
| **Error codes stable** | Same codes, same meanings |
| **Semantics preserved** | `volume` always means the same thing |

### Breaking Changes → New Version

If we ever need breaking changes:
- Introduce `/v2/` prefix
- Run `/v1/` and `/v2/` in parallel
- Deprecate `/v1/` with 6-month runway
- Document migration path

---

## 2. Basic Tier (Current)

### Infrastructure
- **Database**: SQLite (single file)
- **Execution**: Synchronous (blocking)
- **Authentication**: None
- **Deployment**: Single process

### API Surface

#### Control Plane

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/health` | GET | Basic liveness |
| `/health/detailed` | GET | Component checks |
| `/v1/capabilities` | GET | Feature flags |
| `/v1/pipelines` | GET | List pipelines |
| `/v1/pipelines/{name}` | GET | Pipeline details |
| `/v1/pipelines/{name}/run` | POST | Sync execution |

#### Data Plane

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/v1/data/weeks` | GET | Available weeks |
| `/v1/data/symbols` | GET | Top symbols |
| `/v1/data/domains` | GET | List domains (proposed) |
| `/v1/data/calcs` | GET | List calculations (proposed) |
| `/v1/data/calcs/{name}` | GET | Query calculation (proposed) |
| `/v1/data/readiness` | GET | Readiness status (proposed) |
| `/v1/data/anomalies` | GET | Anomaly list (proposed) |

### Capabilities Response

```json
{
  "api_version": "v1",
  "tier": "basic",
  "sync_execution": true,
  "async_execution": false,
  "execution_history": false,
  "authentication": false,
  "scheduling": false,
  "rate_limiting": false,
  "webhook_notifications": false
}
```

---

## 3. Intermediate Tier

### Infrastructure Changes
- **Database**: PostgreSQL (connection pooling)
- **Execution**: Async via LocalBackend (thread pool)
- **Authentication**: Optional API keys
- **Deployment**: Docker Compose (API + DB + Worker)

### New Capabilities

```json
{
  "api_version": "v1",
  "tier": "intermediate",
  "sync_execution": true,
  "async_execution": true,          // ← NEW
  "execution_history": true,         // ← NEW
  "authentication": true,            // ← NEW (optional)
  "scheduling": false,
  "rate_limiting": false,
  "webhook_notifications": false,
  "data_query_enhancements": true,   // ← NEW
  "custom_ordering": true            // ← NEW
}
```

### New Endpoints

#### Execution Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/executions` | POST | Submit async execution |
| `/v1/executions` | GET | List executions (with filters) |
| `/v1/executions/{id}` | GET | Execution details |
| `/v1/executions/{id}/events` | GET | Execution event log |
| `/v1/executions/{id}/cancel` | POST | Cancel running execution |

#### Enhanced Health

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health/ready` | GET | Kubernetes readiness probe |
| `/health/live` | GET | Kubernetes liveness probe |

### Changed Responses

#### Pipeline Run Response (Enhanced)

```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "pipeline": "finra.otc_transparency.ingest_week",
  "status": "queued",
  "poll_url": "/v1/executions/550e8400-e29b-41d4-a716-446655440000",
  "estimated_duration_seconds": 30,  // ← NEW
  "queued_at": "2026-01-04T15:30:00Z"  // ← NEW
}
```

#### Data Query Enhancements

New query parameters on `/v1/data/calcs/{name}`:

| Parameter | Description |
|-----------|-------------|
| `order_by` | Custom ordering (e.g., `symbol:asc`, `volume:desc`) |
| `columns` | Select specific columns |
| `format` | Response format: `json` (default), `csv` |

### Deprecated (Nothing Yet)

No deprecations in Intermediate.

---

## 4. Advanced Tier

### Infrastructure Changes
- **Database**: PostgreSQL (same as Intermediate)
- **Execution**: Celery + Redis/RabbitMQ
- **Authentication**: Required (API keys + service accounts)
- **Deployment**: Docker Compose with message broker

### New Capabilities

```json
{
  "api_version": "v1",
  "tier": "advanced",
  "sync_execution": true,
  "async_execution": true,
  "execution_history": true,
  "authentication": true,
  "scheduling": true,              // ← NEW
  "rate_limiting": true,           // ← NEW
  "webhook_notifications": true,   // ← NEW
  "dead_letter_queue": true,       // ← NEW
  "retry_policies": true,          // ← NEW
  "concurrency_control": true      // ← NEW
}
```

### New Endpoints

#### Dead Letter Queue

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/dead-letters` | GET | List DLQ entries |
| `/v1/dead-letters/{id}` | GET | DLQ entry details |
| `/v1/dead-letters/{id}/retry` | POST | Retry failed execution |
| `/v1/dead-letters/{id}/discard` | POST | Discard entry |

#### Scheduling

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/schedules` | GET | List scheduled jobs |
| `/v1/schedules` | POST | Create schedule |
| `/v1/schedules/{id}` | GET | Schedule details |
| `/v1/schedules/{id}` | DELETE | Remove schedule |
| `/v1/schedules/{id}/pause` | POST | Pause schedule |
| `/v1/schedules/{id}/resume` | POST | Resume schedule |

#### Webhooks

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/webhooks` | GET | List webhook subscriptions |
| `/v1/webhooks` | POST | Create subscription |
| `/v1/webhooks/{id}` | DELETE | Remove subscription |

### Changed Responses

#### Execution Response (Enhanced)

```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "pipeline": "finra.otc_transparency.ingest_week",
  "status": "running",
  "poll_url": "/v1/executions/550e8400-e29b-41d4-a716-446655440000",
  "retry_count": 0,                    // ← NEW
  "max_retries": 3,                    // ← NEW
  "logical_key": "finra:NMS_TIER_1:2025-12-22",  // ← NEW
  "concurrency_group": "finra_ingest"  // ← NEW
}
```

#### Execution Events (New Types)

| Event Type | Description |
|------------|-------------|
| `created` | Execution submitted |
| `queued` | Placed in work queue |
| `started` | Worker began processing |
| `completed` | Finished successfully |
| `failed` | Execution failed |
| `dead_lettered` | Moved to DLQ after max retries |
| `cancelled` | User cancelled |
| `retrying` | Retry attempt starting |

### Deprecated

| Item | Replacement | Notes |
|------|-------------|-------|
| Sync execution default | Async preferred | Sync still works but async is recommended |

---

## 5. Full Tier

### Infrastructure Changes
- **Database**: PostgreSQL (read replicas optional)
- **Execution**: Pluggable backends (Celery, Prefect, Dagster, Temporal)
- **Authentication**: RBAC + OAuth2/OIDC
- **Deployment**: Kubernetes with horizontal scaling
- **Observability**: Prometheus, OpenTelemetry, structured logging

### New Capabilities

```json
{
  "api_version": "v1",
  "tier": "full",
  "sync_execution": true,
  "async_execution": true,
  "execution_history": true,
  "authentication": true,
  "scheduling": true,
  "rate_limiting": true,
  "webhook_notifications": true,
  "dead_letter_queue": true,
  "retry_policies": true,
  "concurrency_control": true,
  "multi_tenant": true,              // ← NEW
  "rbac": true,                      // ← NEW
  "streaming_export": true,          // ← NEW
  "query_caching": true,             // ← NEW
  "cross_domain_queries": true,      // ← NEW
  "data_lineage_api": true           // ← NEW
}
```

### New Endpoints

#### Multi-Tenancy

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/tenants` | GET | List tenants (admin) |
| `/v1/tenants/{id}` | GET | Tenant details |
| `/v1/tenants/{id}/quotas` | GET | Resource quotas |
| `/v1/tenants/{id}/usage` | GET | Usage metrics |

#### RBAC

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/roles` | GET | List roles |
| `/v1/roles/{id}/permissions` | GET | Role permissions |
| `/v1/users/{id}/roles` | GET | User's roles |
| `/v1/users/{id}/roles` | PUT | Assign roles |

#### Streaming Export

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/data/export` | POST | Start export job |
| `/v1/data/export/{id}` | GET | Export status |
| `/v1/data/export/{id}/download` | GET | Download result (signed URL) |

#### Data Lineage

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/lineage/calcs/{name}` | GET | Calc dependencies |
| `/v1/lineage/executions/{id}` | GET | Data produced by execution |
| `/v1/lineage/captures/{id}` | GET | Capture provenance |

#### Cross-Domain Queries

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/data/query` | POST | Multi-domain SQL query |

### Changed Responses

#### Calc Query (Enhanced)

```json
{
  "calc_name": "weekly_symbol_volume_by_tier_v1",
  "calc_version": "v1",
  "query_time": "2026-01-04T15:30:00Z",
  "cache_hit": true,                      // ← NEW
  "cache_age_seconds": 45,                // ← NEW
  "capture": { ... },
  "readiness": { ... },
  "rows": [...],
  "pagination": { ... },
  "query_stats": {                        // ← NEW
    "rows_scanned": 125000,
    "execution_time_ms": 23
  }
}
```

### Deprecated

| Item | Replacement | Notes |
|------|-------------|-------|
| `/v1/data/symbols` | `/v1/data/calcs/weekly_symbol_volume_by_tier_v1` | Keep for backward compat |
| `/v1/data/weeks` | `/v1/data/calcs/available_weeks_v1` | Keep for backward compat |

---

## 6. Migration Guidance

### Basic → Intermediate

**Required Changes:**
1. Update database connection (SQLite → PostgreSQL)
2. Configure connection pool settings
3. Deploy with Docker Compose

**API Client Changes:**
- Check `capabilities.async_execution` and use polling if available
- Optionally switch to async execution for long-running pipelines

**No Breaking Changes**: All Basic endpoints work unchanged.

### Intermediate → Advanced

**Required Changes:**
1. Deploy Redis/RabbitMQ for message broker
2. Configure retry policies
3. Set up DLQ monitoring

**API Client Changes:**
- Handle new execution events (`retrying`, `dead_lettered`)
- Monitor DLQ for failed executions
- Optionally configure webhooks

**No Breaking Changes**: All Intermediate endpoints work unchanged.

### Advanced → Full

**Required Changes:**
1. Migrate to Kubernetes
2. Configure RBAC policies
3. Set up observability stack
4. Configure caching layer

**API Client Changes:**
- Include tenant context in requests (if multi-tenant)
- Handle RBAC permission errors
- Optionally use streaming export for large datasets

**No Breaking Changes**: All Advanced endpoints work unchanged.

---

## 7. Summary Matrix

| Feature | Basic | Intermediate | Advanced | Full |
|---------|-------|--------------|----------|------|
| **Health endpoints** | ✓ | ✓ | ✓ | ✓ |
| **Capabilities discovery** | ✓ | ✓ | ✓ | ✓ |
| **Pipeline list/describe** | ✓ | ✓ | ✓ | ✓ |
| **Sync execution** | ✓ | ✓ | ✓ | ✓ |
| **Async execution** | - | ✓ | ✓ | ✓ |
| **Execution history** | - | ✓ | ✓ | ✓ |
| **Execution events** | - | ✓ (4 types) | ✓ (8 types) | ✓ (10+ types) |
| **Data: weeks/symbols** | ✓ | ✓ | ✓ | ✓ |
| **Data: calcs query** | ✓ | ✓ | ✓ | ✓ |
| **Data: readiness** | ✓ | ✓ | ✓ | ✓ |
| **Data: anomalies** | ✓ | ✓ | ✓ | ✓ |
| **Custom ordering** | - | ✓ | ✓ | ✓ |
| **CSV export** | - | ✓ | ✓ | ✓ |
| **DLQ** | - | - | ✓ | ✓ |
| **Scheduling** | - | - | ✓ | ✓ |
| **Webhooks** | - | - | ✓ | ✓ |
| **Rate limiting** | - | - | ✓ | ✓ |
| **Multi-tenant** | - | - | - | ✓ |
| **RBAC** | - | - | - | ✓ |
| **Streaming export** | - | - | - | ✓ |
| **Cross-domain queries** | - | - | - | ✓ |
| **Data lineage API** | - | - | - | ✓ |
| **Query caching** | - | - | - | ✓ |
