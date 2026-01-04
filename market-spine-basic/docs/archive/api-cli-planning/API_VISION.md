# API Vision

> **Purpose**: Define what the Market Spine API is for, what it intentionally does not do yet, and the guiding principles that will shape its evolution.

---

## What the API Is For

### Primary Mission

The API provides **programmatic access to Market Spine capabilities** that would otherwise require CLI interaction. It enables:

1. **Automation** — CI/CD pipelines, scheduled jobs, and scripts that need to orchestrate data processing
2. **Integration** — External systems (dashboards, alerting, downstream analytics) consuming Market Spine data and status
3. **Observability** — Monitoring tools querying execution status, metrics, and health
4. **Multi-client access** — Web UIs, mobile apps, or multiple concurrent scripts

### Core Principle: CLI and API as Peers

```
                    ┌──────────────────────┐
                    │   Command Layer      │
                    │   (Use Cases)        │
                    │                      │
                    │  • ListPipelines     │
                    │  • DescribePipeline  │
                    │  • RunPipeline       │
                    │  • QueryWeeks        │
                    │  • VerifyData        │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
         ┌─────────┐     ┌─────────┐     ┌─────────────┐
         │   CLI   │     │   API   │     │  Future:    │
         │ (Typer) │     │ (HTTP)  │     │  SDK/gRPC   │
         └─────────┘     └─────────┘     └─────────────┘
```

The API is **not** a wrapper around the CLI. Both CLI and API are **equal citizens** that call the same underlying command layer. This ensures:

- **Behavioral consistency** — Same validation, same normalization, same results
- **No drift** — Changes to business logic automatically reflect in both interfaces
- **Clear testing** — Test the command layer once; adapters are thin

### API Consumers

| Consumer | Tier | Example Use Case |
|----------|------|------------------|
| Scripts | Basic | Cron job running weekly backfills |
| Dashboards | Basic+ | React app showing pipeline status |
| Orchestrators | Intermediate | Airflow/Prefect triggering pipelines |
| Monitoring | Intermediate | Grafana querying execution metrics |
| Multi-tenant apps | Advanced | SaaS platform per-customer isolation |

---

## What the API Does (Basic Tier)

### Pipeline Discovery
- List available pipelines with filtering
- Describe pipeline parameters, types, validation rules
- Show ingest source resolution logic

### Pipeline Execution
- Submit pipeline runs with parameters
- Receive synchronous results (Basic tier)
- Get execution status and metrics

### Data Queries
- Query available weeks per tier
- Query top symbols for a week
- Extensible for future query patterns

### Verification & Health
- Table existence and row counts
- Data integrity checks
- System health diagnostics

---

## What the API Intentionally Does NOT Do (Yet)

These are **deliberate exclusions** for Basic tier, with planned evolution paths:

### 1. Authentication & Authorization
**Not in Basic.** The API is local-only, single-user.

**Future (Intermediate+):**
- API key authentication
- Role-based access control (RBAC)
- Audit logging of API calls

### 2. Asynchronous Execution
**Not in Basic.** All pipeline runs are synchronous.

**Future (Intermediate):**
- Background job queue
- Immediate acknowledgment with polling URL
- WebSocket/SSE for real-time status

### 3. Rate Limiting & Quotas
**Not in Basic.** No protection against API abuse.

**Future (Advanced):**
- Per-client rate limits
- Execution quotas
- Priority queues

### 4. Multi-tenancy
**Not in Basic.** Single database, single user context.

**Future (Full):**
- Tenant isolation
- Per-tenant databases or schemas
- Tenant-aware routing

### 5. Caching
**Not in Basic.** Every request hits the database.

**Future (Intermediate+):**
- Query result caching
- Pipeline list caching
- Execution history caching

### 6. Streaming & WebSockets
**Not in Basic.** HTTP request/response only.

**Future (Advanced):**
- Live execution log streaming
- Real-time pipeline status updates
- Event subscriptions

---

## Guiding Principles

### 1. Contract Stability

The API contract (endpoints, request/response shapes) should remain **stable across tiers**. Evolution happens behind the interface:

```
POST /v1/executions

Basic:       Runs synchronously, returns result
Intermediate: Returns immediately, polls for result
Advanced:    Same + auth headers, tenant context
```

### 2. Explicit Over Implicit

The API should be **more explicit** than the CLI about what's happening:

| CLI (User-Friendly) | API (Machine-Friendly) |
|---------------------|------------------------|
| Auto-derives file path | Requires explicit path OR explicit derivation request |
| Tier aliases work silently | Aliases work, but response shows canonical value |
| Ingest source hidden | Ingest resolution always included in response |

### 3. Progressive Disclosure

Basic tier exposes a **minimal, useful surface**. Advanced features arrive when their tier is built:

```
Basic:        GET /v1/pipelines
Intermediate: GET /v1/pipelines?status=active&owner=me
Advanced:     GET /v1/pipelines?tenant=acme&visibility=shared
```

### 4. Self-Documenting

The API should be **introspectable**:

- OpenAPI spec generated from code
- Parameter schemas derived from pipeline specs
- Examples embedded in responses

### 5. Idempotency-Ready

Even in Basic tier, the API should support **idempotency semantics** to prepare for distributed systems:

```
POST /v1/executions
X-Idempotency-Key: backfill-2025-W01-OTC

# Second request with same key returns cached result
```

---

## Non-Goals

1. **GraphQL** — REST is sufficient; GraphQL adds complexity without clear benefit here
2. **gRPC** — HTTP/JSON is the right choice for web integration; gRPC is premature optimization
3. **Real-time by default** — Polling is acceptable for Basic; SSE/WebSockets come later
4. **Full CRUD for everything** — Some resources (pipelines, domains) are code-defined, not API-mutable
5. **API-first design** — CLI came first; API learns from CLI patterns

---

## Success Criteria

The API is successful when:

1. **A script can replace a CLI command** with a single HTTP call
2. **CLI and API produce identical results** for the same operation
3. **Adding a new pipeline** automatically exposes it via API (no API code changes)
4. **Upgrading to Intermediate** requires no API client changes (only new capabilities)
5. **OpenAPI docs are always accurate** because they're generated from code

---

## Version Strategy

From day one, use versioned paths:

```
/v1/pipelines
/v1/executions
/v1/query/weeks
```

This allows **breaking changes in v2** without disrupting v1 clients. The goal is for v1 to remain stable across all four tiers.
