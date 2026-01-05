# API Overview

> Last Updated: 2026-01-04  
> Version: 1.0  
> Status: **AUTHORITATIVE**

This document defines the architecture and terminology for the Market Spine API. All other API documentation in `docs/api/` builds on these foundations.

---

## 1. Two API Planes

Market Spine exposes two distinct API surfaces:

| Plane | Prefix | Purpose | Audience |
|-------|--------|---------|----------|
| **Control Plane** | `/v1/pipelines`, `/v1/executions`, `/health` | Operations: run pipelines, track executions, monitor health | Operators, CI/CD, Dashboards |
| **Data Plane** | `/v1/data/*` | Query domain data: tables, calcs, readiness, anomalies | Analysts, Trading Desks, Applications |

### Control Plane (Operations API)

The control plane manages the *execution* of data processing:

- **Pipelines**: List, describe, and trigger data pipelines
- **Executions**: Submit, poll, cancel, retry pipeline runs
- **Health**: Liveness, readiness, and detailed component checks
- **Capabilities**: Discover tier features for client adaptation

Control plane operations are *imperative* ("do this") and typically mutate state.

### Data Plane (Query API)

The data plane provides *read-only* access to processed data:

- **Tables**: Raw, normalized, and aggregated data tables
- **Calcs**: Derived calculations (venue share, weekly volume, etc.)
- **Readiness**: Whether data is ready for a given use case
- **Anomalies**: Data quality issues detected during processing

Data plane operations are *declarative* ("give me this") and never mutate state.

---

## 2. Core Terminology

### Domain

A **domain** is a logical grouping of related data and business rules. Examples:

- `finra.otc_transparency` — FINRA OTC weekly transparency data
- `exchange.nyse_trades` — NYSE trade data (future)
- `analytics.venue_quality` — Cross-domain venue analysis (future)

Domains are namespaced using dot notation: `{source}.{dataset}` or `{category}.{name}`.

### Dataset

A **dataset** is a logical table within a domain. Datasets have lifecycle stages:

| Stage | Description | Example Table |
|-------|-------------|---------------|
| `raw` | Ingested as-is from source | `finra_otc_raw` |
| `normalized` | Cleaned, typed, validated | `finra_otc_normalized` |
| `aggregated` | Summarized/pivoted | `finra_otc_weekly_by_venue` |

### Calc

A **calc** (calculation) is a derived metric or score computed from one or more datasets. Calcs are:

- **Versioned**: Each calc has a version (e.g., `venue_share_v1`, `venue_share_v2`)
- **Reproducible**: Given the same inputs, produces the same outputs
- **Documented**: Has a description, formula, and dependency list

Example calcs:
- `weekly_symbol_volume_by_tier_v1` — Total volume per symbol/tier/week
- `venue_share_v1` — Venue's share of total volume for a symbol
- `concentration_score_v1` — HHI-based venue concentration metric

### Version

**Version** applies to both calcs and API contracts:

- **Calc version**: `v1`, `v2`, etc. Allows evolution without breaking consumers
- **API version**: `v1` prefix on routes. Breaking changes require new version

Calcs may be deprecated but remain queryable. The response includes deprecation metadata.

### Capture ID

A **capture_id** uniquely identifies a specific data snapshot:

```
finra.otc_transparency:NMS_TIER_1:2025-12-22:20251223
└────── domain ───────┘ └─ tier ─┘ └─ week ─┘ └─ date ─┘
```

Capture IDs enable:
- **Point-in-time queries**: Replay data as it existed at a specific capture
- **Lineage tracking**: Trace processed data back to source
- **Debugging**: Compare outputs across captures

### Captured At

The **captured_at** timestamp records *when* data was ingested into the system (not when it was published by the source). This enables:

- **Audit trails**: When did we receive this data?
- **Debugging**: Why does this capture differ from the previous?
- **Reprocessing**: Which captures need to be rerun?

### Readiness

**Readiness** indicates whether a data partition is suitable for a specific use case:

| Field | Type | Description |
|-------|------|-------------|
| `is_ready` | boolean | Master readiness flag |
| `ready_for` | string | Use case: `production`, `internal`, `testing` |
| `raw_complete` | boolean | Raw ingestion finished |
| `normalized_complete` | boolean | Normalization finished |
| `calc_complete` | boolean | All calcs computed |
| `no_critical_anomalies` | boolean | No blocking quality issues |

**Critical distinction**: `latest` data is not automatically `ready`. Data flows through:

```
Ingested → Normalized → Calculated → Quality-checked → Ready
```

Consumers must check readiness before treating data as authoritative.

### Anomalies

**Anomalies** are data quality issues detected during processing:

| Field | Type | Description |
|-------|------|-------------|
| `anomaly_type` | string | Machine-readable type (e.g., `MISSING_VENUE`) |
| `severity` | enum | `CRITICAL`, `ERROR`, `WARN`, `INFO` |
| `category` | string | `INGESTION`, `NORMALIZATION`, `CALCULATION`, `VALIDATION` |
| `message` | string | Human-readable description |
| `details` | object | Structured context (row numbers, values, etc.) |
| `detected_at` | timestamp | When the anomaly was detected |
| `resolved_at` | timestamp | When/if resolved (null if open) |

Anomalies with `severity=CRITICAL` block readiness. Others are informational.

---

## 3. Stable Contract Philosophy

### Design Principles

1. **Small but extensible**: Basic tier exposes minimal endpoints that don't constrain future tiers
2. **Additive evolution**: New features add endpoints/fields; existing contracts rarely change
3. **Capability-driven**: Clients discover features via `/v1/capabilities`, not version sniffing
4. **Registry-driven**: New domains/calcs plug in without code changes to API routes
5. **Consistent shapes**: All data responses use the same envelope format

### What "Stable" Means

| Guarantee | Description |
|-----------|-------------|
| **Field presence** | Fields in responses will not be removed within a major version |
| **Field types** | Field types will not change (string stays string) |
| **Additive only** | New fields may appear; clients must ignore unknown fields |
| **Semantic stability** | Field meanings don't change (volume always means shares traded) |
| **Deprecation before removal** | Deprecated fields marked before removal (minimum 2 releases) |

### What May Change

| Change Type | Allowed? | Notes |
|-------------|----------|-------|
| Add optional field | ✓ | Clients ignore unknown fields |
| Add new endpoint | ✓ | New functionality |
| Add new error code | ✓ | Clients handle unknown codes gracefully |
| Add new calc version | ✓ | Old versions remain available |
| Remove deprecated field | ✓ | After deprecation period |
| Change field semantics | ✗ | Would break consumers |
| Remove endpoint | ✗ | Within major version |
| Change required→optional | ✓ | Safe loosening |
| Change optional→required | ✗ | Would break existing calls |

---

## 4. Tier Progression

Market Spine has four tiers with increasing capabilities:

| Tier | Database | Execution | Key Features |
|------|----------|-----------|--------------|
| **Basic** | SQLite | Synchronous | CLI + minimal API, single-user |
| **Intermediate** | PostgreSQL | Async (local) | Full API, execution history, multi-user |
| **Advanced** | PostgreSQL | Async (Celery) | DLQ, concurrency, retry policies |
| **Full** | PostgreSQL | Async (pluggable) | Multi-tenant, RBAC, streaming, caching |

Each tier:
- **Implements** all endpoints from lower tiers
- **Extends** responses with additional fields (where applicable)
- **Adds** new endpoints for new capabilities
- **Never removes** endpoints from lower tiers

See [03-intermediate-advanced-full-roadmap.md](03-intermediate-advanced-full-roadmap.md) for detailed evolution.

---

## 5. Cross-References

| Document | Purpose |
|----------|---------|
| [01-data-access-patterns.md](01-data-access-patterns.md) | Query patterns, pagination, response envelopes |
| [02-basic-api-surface.md](02-basic-api-surface.md) | Complete Basic tier endpoint reference |
| [03-intermediate-advanced-full-roadmap.md](03-intermediate-advanced-full-roadmap.md) | Evolution roadmap by tier |
| [04-openapi-and-testing-strategy.md](04-openapi-and-testing-strategy.md) | OpenAPI conventions, testing approach |
| [../frontend-backend-integration-map.md](../frontend-backend-integration-map.md) | Frontend client adaptation guide |
| [../tier-comparison.md](../tier-comparison.md) | Feature matrix across all tiers |

---

## 6. Assumptions

This document makes the following assumptions (document explicitly for future reference):

1. **Single-domain focus initially**: Basic starts with FINRA OTC only; multi-domain comes later
2. **Read-heavy workload**: Data plane is optimized for reads; writes happen via pipelines
3. **No real-time streaming**: All queries are request/response; streaming is Full tier only
4. **Capture-based versioning**: Data is versioned by capture, not by user-defined versions
5. **UTC timestamps**: All timestamps are UTC; clients handle timezone conversion
6. **English-only**: Error messages and documentation are English only
7. **No partial responses**: Queries return complete results or error; no partial success
