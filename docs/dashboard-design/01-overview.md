# Dashboard Architecture Overview

> Part of: [Dashboard Design](00-index.md)

## System Context

Market Spine is an **operational data platform** for financial market data:

```
┌─────────────────────────────────────────────────────────────────┐
│                     MARKET SPINE PLATFORM                        │
├─────────────────────────────────────────────────────────────────┤
│  Data Sources          │  Processing            │  Consumers    │
│  ─────────────         │  ──────────            │  ─────────    │
│  • FINRA OTC files     │  • Ingest pipelines    │  • Quants     │
│  • Exchange calendars  │  • Normalize pipelines │  • Traders    │
│  • Alpha Vantage API   │  • Compute pipelines   │  • Compliance │
│  • Manual uploads      │  • Backfill pipelines  │  • Systems    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Dashboard Purpose

The dashboard serves as the **control plane** for operators who need to:

| Need | Dashboard Role |
|------|----------------|
| Monitor health | Surface failures before users report them |
| Debug issues | Show execution context, not just error messages |
| Validate data | Certify data readiness for downstream use |
| Track changes | Highlight what changed and when |
| Plan actions | Show what's scheduled vs what's due |
| Prevent mistakes | Block dangerous operations contextually |

---

## Core Concepts

### Pipeline

A named, parameterized data processing unit:
- `finra.otc_transparency.ingest_week`
- `finra.otc_transparency.normalize_week`
- `analytics.volume_metrics.compute`

### Execution

A single run of a pipeline with:
- `execution_id`: UUID
- `capture_id`: Point-in-time identifier for data versioning
- `status`: pending → running → completed/failed
- `timing`: started_at, completed_at, duration
- `params`: Input parameters for this run

### Data Asset

A logical dataset produced by pipelines:
- Tier: OTC, NMS_TIER_1, NMS_TIER_2
- Week: Temporal partition
- Readiness: certified, preliminary, blocked

### Capture Semantics

Every data mutation is associated with a `capture_id`:
- Enables point-in-time replay
- Tracks lineage from source to derived
- Supports revision detection

---

## Operational States

The system has three primary health states:

| State | Meaning | Dashboard Presentation |
|-------|---------|----------------------|
| 🟢 **Healthy** | All scheduled runs succeeded, data is current | Green indicators, minimal attention needed |
| 🟡 **Warning** | Some runs delayed or data is stale | Yellow indicators, surface in overview |
| 🔴 **Critical** | Failures blocking data availability | Red indicators, prominent alerts |

---

## Key Metrics Categories

### Pipeline Health
- Success rate (24h, 7d)
- Average duration vs historical
- Last successful run timestamp
- Failure streak count

### Data Freshness
- Latest available week per tier
- Time since last update
- Expected vs actual update time
- Staleness threshold breach

### Quality Signals
- Anomaly count by severity
- Data completeness percentage
- Validation rule failures
- Schema drift detection

### Operational Load
- Executions in progress
- Queue depth (if applicable)
- Resource utilization
- Rate limit headroom

---

## Navigation Model

```
┌──────────────────────────────────────────────────────────────┐
│  HEADER: Health indicator | Tier badge | User | Settings    │
├──────────────────────────────────────────────────────────────┤
│  SIDEBAR              │  MAIN CONTENT                        │
│  ───────              │  ────────────                        │
│  Overview ★           │  [Page-specific content]             │
│  Pipelines            │                                       │
│  Executions           │                                       │
│  ─────────            │                                       │
│  Data Readiness       │                                       │
│  Quality              │                                       │
│  Assets               │                                       │
│  ─────────            │                                       │
│  Settings             │                                       │
└──────────────────────────────────────────────────────────────┘
```

Navigation groups:
1. **Operations**: Overview, Pipelines, Executions
2. **Data**: Readiness, Quality, Assets
3. **System**: Settings

---

## Tier Influence on UI

| Feature | Basic | Intermediate | Advanced |
|---------|-------|--------------|----------|
| Pipeline list | ✅ | ✅ | ✅ |
| Sync execution | ✅ | ✅ | ✅ |
| Execution history | ❌ | ✅ | ✅ |
| Scheduling | ❌ | ✅ | ✅ |
| Async execution | ❌ | ✅ | ✅ |
| Quality dashboard | ❌ | ✅ | ✅ |
| Data lineage | ❌ | ❌ | ✅ |
| Alerting | ❌ | ❌ | ✅ |
| Multi-tenant | ❌ | ❌ | ✅ |

The UI adapts by:
- Showing capability-appropriate pages
- Displaying upgrade prompts (not hiding randomly)
- Maintaining consistent navigation structure
