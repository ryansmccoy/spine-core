# Market Spine Contract Clarifications & Invariants

> Last Updated: 2026-01-04  
> Version: 1.0  
> Status: **AUTHORITATIVE ADDENDUM**  
> Audience: Senior engineers, quants, system integrators

This document supplements the [API documentation set](README.md) with formal invariants, guarantees, and operational contracts. It is not a tutorial—it defines what the system **must** do, not how to use it.

---

## 1. Capture & Time Semantics

### 1.1 Capture ID Contract

A `capture_id` uniquely identifies a **specific ingestion of a specific logical partition**.

**Format:**
```
{domain}:{partition_key}:{capture_timestamp}
```

Where `partition_key` is domain-specific (e.g., `{tier}:{week_ending}` for FINRA OTC).

**Example:**
```
finra.otc_transparency:NMS_TIER_1:2025-12-22:20251223
└────── domain ───────┘└───── partition_key ────┘└ date ┘
                        └─ tier ─┘└── week ──┘
```

**Invariants:**

| Property | Guarantee |
|----------|-----------|
| **Uniqueness** | A `capture_id` is globally unique within a deployment. Two ingestions of the same logical partition on the same day produce different `capture_id` values (via timestamp or hash suffix). |
| **Immutability** | Once a capture exists, its row data is **never modified**. Corrections create new captures. |
| **Scope** | A capture spans exactly one `(domain, partition_key)` tuple. Cross-partition captures are prohibited. |
| **Referential integrity** | All rows in `*_normalized` and `*_aggregated` tables reference a valid `capture_id`. Orphaned rows are invalid state. |

**Non-guarantees:**

- Capture IDs are **not** globally sequential
- Capture IDs are **not** cryptographically secure (use for lineage, not auth)
- The format is **not** part of the stable contract (parse via API, not regex)

### 1.2 Temporal Model

Three distinct timestamps govern data:

| Clock | Field | Semantics | Mutability |
|-------|-------|-----------|------------|
| **Business time** | `week_ending`, `trade_date` | The period the data *represents* | Immutable after ingest |
| **Source time** | `last_update_date`, `published_at` | When the source *claims* it was updated | Immutable after ingest |
| **Capture time** | `captured_at` | When *we* ingested the data | Immutable after ingest |

**Invariants:**

1. `captured_at` is always UTC
2. `captured_at >= source_time` (we cannot capture before publication)
3. `business_time` may be in the future relative to `captured_at` (forward-looking data)
4. All three clocks are preserved independently—none is derived from another

### 1.3 Re-ingestion & Reprocessing Rules

| Scenario | Behavior | Capture ID |
|----------|----------|------------|
| **Re-ingest same file** | Creates new capture with new `capture_id` | New |
| **Re-ingest corrected file** | Creates new capture; old capture remains | New |
| **Reprocess existing capture** | Uses same `capture_id`; overwrites derived tables via DELETE+INSERT | Same |
| **Force re-run of pipeline** | Depends on `--force` flag; may skip or recompute | Same or New |

**Invariant:** Reprocessing a capture **never** modifies the raw layer. Only normalized/aggregated layers may be recomputed.

### 1.4 Multi-Capture Dependencies

Calcs **may** depend on multiple captures under these constraints:

| Rule | Description |
|------|-------------|
| **Same domain required** | Cross-domain multi-capture dependencies are prohibited in Basic/Intermediate. Full tier relaxes this constraint with explicit lineage tracking. |
| **Explicit declaration** | Multi-capture calcs must declare all upstream captures in metadata |
| **Partial availability** | If any upstream capture is missing, the calc returns `DEPENDENCY_MISSING` error |
| **No implicit latest** | Multi-capture calcs must specify exact `capture_id` values, not "latest". Full tier may support pinned "latest" aliases with audit logging. |

---

## 2. Idempotency & Execution Guarantees

### 2.1 Idempotency Definition

A pipeline execution is **idempotent** if:

> Running the same pipeline with the same logical parameters produces the same observable outcome, regardless of how many times it is invoked.

"Same observable outcome" means:
- Same rows in target tables (content, not timestamps)
- Same quality/reject records
- Same manifest entry

### 2.2 Idempotency Keys

Pipeline idempotency is determined by a composite key:

| Component | Purpose | Example |
|-----------|---------|---------|
| `pipeline_name` | Which pipeline | `finra.otc_transparency.ingest_week` |
| `logical_key` | Business partition | `NMS_TIER_1:2025-12-22` |
| `params_hash` | Normalized parameter hash | `sha256(sorted(params))[:16]` |
| `version` | Pipeline code version | `v1.2.0` |

**Invariant:** Two executions with identical `(pipeline_name, logical_key, params_hash, version)` are considered duplicates.

### 2.3 Duplicate Handling by Tier

| Tier | Duplicate Detection | Behavior |
|------|---------------------|----------|
| **Basic** | Manifest lookup (sync) | Skip if manifest entry exists; execute if `--force` |
| **Intermediate** | Manifest + execution table | Reject with `409 Conflict` if in-progress; skip if completed |
| **Advanced** | Manifest + execution + logical_key lock | Queue with dedup; one execution per logical_key at a time |
| **Full** | Same as Advanced + distributed lock | Cross-node deduplication via Redis/Postgres advisory locks |

### 2.4 Execution Guarantees

| Guarantee | Basic | Intermediate | Advanced | Full |
|-----------|-------|--------------|----------|------|
| **At-most-once** (no duplicate runs) | ✓ (via manifest) | ✓ | ✓ | ✓ |
| **At-least-once** (retries on failure) | ✗ | ✗ | ✓ (DLQ + retry) | ✓ |
| **Exactly-once** (single successful run) | ✓ (sync) | Best-effort | Best-effort | Best-effort |
| **Ordering** | FIFO (single-threaded) | FIFO per lane | FIFO per logical_key | Configurable |

**Clarification:** "Exactly-once" in distributed systems is a spectrum. Advanced/Full provide *effective* exactly-once via idempotent pipelines + deduplication, not transactional guarantees.

### 2.5 Retry Semantics

| Tier | Retry Policy | Max Attempts | Backoff |
|------|--------------|--------------|---------|
| **Basic** | None (manual re-run) | 1 | N/A |
| **Intermediate** | None (manual re-run) | 1 | N/A |
| **Advanced** | Configurable per pipeline | Default: 3 | Exponential (1s, 2s, 4s) |
| **Full** | Policy-driven (per pipeline class) | Configurable | Exponential + jitter |

**Invariant:** A pipeline that exhausts retries moves to DLQ. DLQ entries require explicit human action.

### 2.6 Atomicity Guarantees

Pipeline execution is **all-or-nothing** at the logical partition level:

| Outcome | Database State | Manifest Entry |
|---------|----------------|----------------|
| **Success** | All rows written | `completed` |
| **Failure** | Rolled back (no partial writes) | `failed` or absent |
| **Dry run** | No writes | `dry_run` |

**Invariant:** A pipeline never leaves partial data in target tables. If a pipeline fails mid-execution, the transaction is rolled back. Callers will never observe half-written partitions.

**Note:** Atomicity is per-partition, not per-execution. A pipeline processing multiple partitions may succeed on some and fail on others (each partition is an independent transaction).

---

## 3. Calc Dependency Model

### 3.1 Dependency Graph

Calcs form a **directed acyclic graph (DAG)**:

```
finra_otc_raw
      │
      ▼
finra_otc_normalized
      │
      ├──────────────────┬──────────────────┐
      ▼                  ▼                  ▼
weekly_symbol_volume   venue_share      concentration_score
      │                  │
      └────────┬─────────┘
               ▼
        symbol_quality_score (future)
```

### 3.2 Dependency Declaration

Each calc declares its upstream dependencies:

```python
@dataclass
class CalcDefinition:
    name: str
    version: str
    upstream_tables: list[str]      # Tables this calc reads
    upstream_calcs: list[str]       # Calcs this calc depends on
    output_table: str               # Table this calc writes to
```

**Invariants:**

1. **No cycles**: The dependency graph must be acyclic. Cycles are a configuration error.
2. **Version pinning**: A calc depends on specific upstream *versions*, not "latest". Full tier supports version ranges with deprecation warnings.
3. **Explicit declaration**: Implicit dependencies (e.g., via SQL JOINs not declared) are invalid

### 3.3 Invalidation Rules

| Change | Downstream Impact | Automatic Recompute |
|--------|-------------------|---------------------|
| New capture ingested | Downstream calcs stale | No (explicit trigger required) |
| Upstream calc recomputed | Downstream calcs stale | No (explicit trigger required) |
| Calc version change | Downstream calcs invalid | No (explicit trigger required) |
| Upstream schema change | Downstream calcs may break | No (fails on next run) |

**Invariant:** Staleness is **not** automatically resolved. Pipelines must be explicitly triggered. This prevents cascade failures.

### 3.4 Lineage Model (Conceptual)

The dependency graph enables future lineage queries:

| Query Type | Answers |
|------------|---------|
| **Forward lineage** | "What calcs depend on this capture?" |
| **Backward lineage** | "What captures does this calc row derive from?" |
| **Impact analysis** | "If this capture is bad, what is affected?" |
| **Freshness propagation** | "When was the oldest upstream capture for this calc?" |

This is a **data model** commitment, not an API commitment. Lineage APIs are Full-tier only.

---

## 4. Data Retention & Growth Considerations

### 4.1 Unbounded Entities

| Entity | Growth Rate | Pruning Safety |
|--------|-------------|----------------|
| **Captures** (raw layer) | O(ingestions) | **Unsafe** without business approval |
| **Normalized data** | O(captures × rows) | Safe to recompute from raw |
| **Calc outputs** | O(captures × calcs) | Safe to recompute from normalized |
| **Executions** | O(pipeline runs) | Safe after retention period |
| **Execution events** | O(executions × events) | Safe after retention period |
| **Anomalies** | O(data quality issues) | Safe if resolved + aged out |
| **Manifest entries** | O(pipeline runs) | **Unsafe** (breaks idempotency) |
| **DLQ entries** | O(failures) | Safe after resolution |

### 4.2 Retention Policies by Tier

| Entity | Basic | Intermediate | Advanced | Full |
|--------|-------|--------------|----------|------|
| Raw captures | Forever | Forever | 2 years | Policy-driven |
| Normalized data | Forever | 1 year | 1 year | Policy-driven |
| Calc outputs | Forever | 1 year | 1 year | Policy-driven |
| Executions | Forever | 90 days | 90 days | 30-90 days |
| Execution events | N/A | 30 days | 30 days | 14 days |
| Anomalies | Forever | 1 year | 1 year | 90 days |
| Manifest | Forever | Forever | Forever | Forever |

**Invariant:** Manifest entries are **never** pruned. They are the source of truth for idempotency.

**Scaling note:** Because manifest entries are append-only, the table grows O(pipeline runs). Implementations must ensure the manifest table has appropriate indexes on `(pipeline_name, logical_key)` for idempotency lookups. In Full tier with high execution volume (>1M entries), consider partitioning by `created_at` month while maintaining index coverage.

### 4.3 Safe Compaction Operations

| Operation | Safety | Notes |
|----------|--------|-------|
| Delete old execution records | ✓ | After retention period |
| Delete resolved anomalies | ✓ | After retention + grace period |
| Delete DLQ entries | ✓ | After explicit discard/retry |
| Delete old calc outputs | ✓ | If raw + normalized preserved |
| Delete old normalized data | ⚠️ | Only if raw preserved + recalc possible |
| Delete old raw captures | ❌ | Business decision, not technical |
| Truncate manifest | ❌ | Breaks idempotency guarantees |

### 4.4 Storage Metrics Exposure

| Metric | Basic | Intermediate+ |
|--------|-------|---------------|
| Table row counts | CLI: `spine db stats` | API: `/v1/ops/storage` |
| Database size | CLI: `spine db stats` | API: `/v1/ops/storage` |
| Growth rate | Manual | Dashboard widget |
| Retention compliance | Manual | Alerting |

---

## 5. Readiness & Frontend Consumption Rules

### 5.1 Readiness State Machine

```
              ┌─────────────────────────────────────────────┐
              │                                             │
              ▼                                             │
┌──────────────────┐    ┌──────────────────┐    ┌──────────┴───────┐
│  RAW_COMPLETE    │───▶│ NORM_COMPLETE    │───▶│  CALC_COMPLETE   │
│  (ingested)      │    │ (normalized)     │    │  (calculated)    │
└──────────────────┘    └──────────────────┘    └──────────────────┘
                                                         │
                                                         ▼
                                                ┌──────────────────┐
                                                │  READY           │
                                                │  (no critical    │
                                                │   anomalies)     │
                                                └──────────────────┘
```

**Invariant:** Readiness is **monotonic** within a capture. Once a stage is complete, it does not regress. A new capture restarts the state machine.

### 5.2 Client Consumption Rules

| Scenario | Client Behavior | HTTP Status |
|----------|-----------------|-------------|
| Data ready, latest capture | Use data | 200 |
| Data ready, old capture (as-of query) | Use data, note `is_latest: false` | 200 |
| Data exists but not ready | **Block or degrade** (client choice) | 409 `DATA_NOT_READY` |
| Data does not exist | Show empty state | 404 |
| Partial readiness (some tiers ready) | Show available, indicate pending | 200 (partial) |

### 5.3 Frontend Behavior Contracts

| Condition | Required Behavior | Optional Behavior |
|-----------|-------------------|-------------------|
| `is_ready: true` | Display data as authoritative | — |
| `is_ready: false` | Display warning/banner | Auto-refresh, show stale data with indicator |
| `blocking_issues: [...]` | Display issues to user | Link to anomaly details |
| `capture.is_latest: false` | Indicate historical view | Show "newer data available" link |
| `calc_deprecated: true` | Log warning (console) | Show deprecation notice in UI |

### 5.4 Graceful Degradation Pattern

```typescript
async function queryWithFallback(calcName: string, params: QueryParams): Promise<CalcResult> {
  try {
    const result = await spineClient.queryCalc(calcName, params);
    
    if (!result.readiness.is_ready) {
      // Option A: Block
      throw new DataNotReadyError(result.readiness.blocking_issues);
      
      // Option B: Degrade (show with warning)
      return { ...result, _stale: true, _warning: "Data processing in progress" };
    }
    
    return result;
  } catch (error) {
    if (error.code === 'DATA_NOT_READY') {
      // Retry with exponential backoff, or show pending state
      return { _pending: true, _retryAfter: 30 };
    }
    throw error;
  }
}
```

### 5.5 Polling & Refresh

| Scenario | Recommended Approach |
|----------|----------------------|
| Waiting for data to become ready | Poll `/v1/data/readiness` every 30s, max 10 attempts |
| Checking for new captures | Poll `/v1/data/weeks` on page load, not continuously |
| Real-time updates | Not supported in Basic/Intermediate; use webhooks in Advanced+ |

**Invariant:** Clients must implement backoff. Aggressive polling (< 10s) may be rate-limited in Advanced+.

---

## 6. Cross-Reference to Existing Documentation

| Topic | Primary Document | This Addendum Section |
|-------|------------------|----------------------|
| API overview | [00-api-overview.md](00-api-overview.md) | §1 (Capture semantics) |
| Query patterns | [01-data-access-patterns.md](01-data-access-patterns.md) | §5 (Readiness rules) |
| Basic endpoints | [02-basic-api-surface.md](02-basic-api-surface.md) | §4 (Retention) |
| Tier evolution | [03-intermediate-advanced-full-roadmap.md](03-intermediate-advanced-full-roadmap.md) | §2 (Guarantees by tier) |
| Testing | [04-openapi-and-testing-strategy.md](04-openapi-and-testing-strategy.md) | — |

---

## 7. Summary of Hard Invariants

These invariants are **non-negotiable**. Violations are bugs.

| # | Invariant |
|---|-----------|
| 1 | `capture_id` is globally unique and immutable |
| 2 | Raw layer data is never modified after ingestion |
| 3 | All timestamps are UTC |
| 4 | Manifest entries are never deleted |
| 5 | Calc dependency graphs are acyclic |
| 6 | Downstream staleness is not automatically resolved |
| 7 | Readiness is monotonic within a capture |
| 8 | `is_ready: false` means data should not be treated as authoritative |
| 9 | Reprocessing uses DELETE+INSERT, never UPDATE |
| 10 | Cross-domain multi-capture dependencies are prohibited in Basic/Intermediate |
| 11 | Pipeline execution is atomic per-partition (no partial writes) |
