# Page Spec: Data Readiness

> Part of: [Dashboard Design](00-index.md)

## Page Identity

| Attribute | Value |
|-----------|-------|
| Route | `/dashboard/readiness` |
| Primary Question | Is data safe to use for trading/research? |
| Secondary Questions | What's certified? What's preliminary? What's blocked? |
| Primary Persona | Quant / Analyst |
| Tier Required | Basic (limited), Intermediate (full) |

---

## Primary Question

> **Is data safe to use for trading/research?**

The analyst needs to know:
1. Can I trust this data for production use?
2. What's the most recent data available?
3. Are there any known issues I should be aware of?

---

## Core Concept: Readiness States

| State | Badge | Meaning |
|-------|-------|---------|
| 🟢 **Certified** | `CERTIFIED` | Quality-checked, safe for production use |
| 🟡 **Preliminary** | `PRELIMINARY` | Ingested but not yet validated |
| 🔴 **Blocked** | `BLOCKED` | Known issues prevent use |
| ⬜ **Missing** | `NOT AVAILABLE` | Data not yet ingested |

---

## Page Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Data Readiness                              As of: 5 min ago  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────┐ ┌─────────────────────┐                │
│  │ OTC                 │ │ NMS Tier 1          │                │
│  │ ════════════════    │ │ ════════════════    │                │
│  │ Latest: 2025-12-22  │ │ Latest: 2025-12-22  │                │
│  │ Status: CERTIFIED ✓ │ │ Status: PRELIMINARY │                │
│  │ Symbols: 2,847      │ │ Symbols: 8,234      │                │
│  │ Coverage: 12 weeks  │ │ Coverage: 8 weeks   │                │
│  └─────────────────────┘ └─────────────────────┘                │
│                                                                  │
│  ┌─────────────────────┐                                        │
│  │ NMS Tier 2          │                                        │
│  │ ════════════════    │                                        │
│  │ Latest: 2025-12-15  │                                        │
│  │ Status: BLOCKED ⚠   │                                        │
│  │ Reason: Missing     │                                        │
│  │ calendar dependency │                                        │
│  └─────────────────────┘                                        │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  DETAILED READINESS BY WEEK                                     │
│  ═══════════════════════════                                    │
│                                                                  │
│  [OTC]  [NMS Tier 1]  [NMS Tier 2]                             │
│                                                                  │
│  WEEK ENDING  │ STATUS      │ SYMBOLS │ ANOMALIES │ CERTIFIED  │
│  ──────────────────────────────────────────────────────────────│
│  2025-12-22   │ CERTIFIED   │ 2,847   │ 0         │ Jan 3      │
│  2025-12-15   │ CERTIFIED   │ 2,812   │ 1 minor   │ Dec 27     │
│  2025-12-08   │ CERTIFIED   │ 2,798   │ 0         │ Dec 20     │
│  2025-12-01   │ PRELIMINARY │ 2,765   │ 2 minor   │ —          │
│  2025-11-24   │ BLOCKED     │ 2,701   │ 1 critical│ —          │
│  2025-11-17   │ CERTIFIED   │ 2,689   │ 0         │ Nov 22     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Metrics

### Tier Summary Card

| Metric | Source | Calculation |
|--------|--------|-------------|
| `latest_week` | `/v1/data/weeks?tier=X&limit=1` | Most recent week_ending |
| `readiness_status` | `/v1/data/readiness?tier=X` | certified/preliminary/blocked |
| `symbol_count` | `/v1/data/weeks` | symbol_count for latest week |
| `coverage_weeks` | `/v1/data/weeks` | Total weeks available |

### Week Detail Row

| Metric | Source | Notes |
|--------|--------|-------|
| `week_ending` | Week | Date string |
| `status` | Readiness | Certification state |
| `symbol_count` | Week | Number of symbols |
| `anomaly_count` | Quality | Count by severity |
| `certified_at` | Readiness | When certified (if applicable) |
| `certified_by` | Readiness | User or system |

---

## Completeness Visualization

### Rolling Window Indicator

For derived analytics that require N weeks of history:

```
Volume 6-Week Average Readiness
═══════════════════════════════

Required: 6 consecutive weeks
Available: [✓][✓][✓][✓][✓][✓]  6/6 ✓ READY

Week-over-Week Change Readiness
═══════════════════════════════

Required: 2 consecutive weeks
Available: [✓][✓]  2/2 ✓ READY
```

### Gap Visualization

```
OTC Data Coverage (Last 12 weeks)
═════════════════════════════════

     Dec 22  Dec 15  Dec 08  Dec 01  Nov 24  Nov 17  ...
        ✓       ✓       ✓       ⚠       ✕       ✓
     CERT    CERT    CERT   PRELIM  BLOCK   CERT

⚠ Week of Nov 24 has 1 critical anomaly blocking certification
```

---

## Dependency Tracking

### Upstream Dependencies

```
finra.nms_tier1.normalized (2025-12-22)
═══════════════════════════════════════

DEPENDENCIES:
├── exchange_calendars.nyse_2025  ✓ Available
├── exchange_calendars.nasdaq_2025  ✓ Available
└── finra.nms_tier1.raw (2025-12-22)  ⚠ Preliminary

STATUS: PRELIMINARY
REASON: Upstream raw data not yet certified
```

### Downstream Impact

```
If finra.otc.normalized (2025-12-22) is revised:
═══════════════════════════════════════════════

AFFECTED DERIVED DATA:
├── analytics.volume_6w_avg (2025-12-22)  → Will be stale
├── analytics.wow_change (2025-12-22)  → Will be stale
└── analytics.top_movers (2025-12-22)  → Will be stale

RECOMMENDATION: Re-run compute pipelines after revision
```

---

## Actions

### Certify Data (Intermediate+)

For authorized users to mark data as certified:

```
┌───────────────────────────────────────────┐
│  Certify Data                             │
│                                           │
│  Tier: OTC                                │
│  Week: 2025-12-22                         │
│                                           │
│  Pre-certification checks:                │
│  ✓ All symbols ingested                   │
│  ✓ No critical anomalies                  │
│  ⚠ 2 minor anomalies (acknowledged)       │
│                                           │
│  ☑ I confirm this data is ready for       │
│    production use                         │
│                                           │
│             [Cancel]  [Certify]           │
└───────────────────────────────────────────┘
```

### Block Data

For marking data as unusable:

```
┌───────────────────────────────────────────┐
│  Block Data                               │
│                                           │
│  Tier: NMS Tier 2                         │
│  Week: 2025-11-24                         │
│                                           │
│  Reason: [________________________]       │
│          [________________________]       │
│                                           │
│  This will:                               │
│  • Mark data as BLOCKED                   │
│  • Notify downstream consumers            │
│  • Require manual unblock                 │
│                                           │
│             [Cancel]  [Block Data]        │
└───────────────────────────────────────────┘
```

---

## Failure States

### No Data Available

```
┌─────────────────────────────────────┐
│  📊 No Data Yet                     │
│                                     │
│  No data has been ingested for      │
│  this tier.                         │
│                                     │
│  Run an ingest pipeline to          │
│  populate data.                     │
│                                     │
│  [Go to Pipelines]                  │
└─────────────────────────────────────┘
```

### Readiness Service Unavailable

```
┌─────────────────────────────────────┐
│  ⚠️ Readiness Check Failed         │
│                                     │
│  Could not determine readiness      │
│  status. Data may still be          │
│  available for query.               │
│                                     │
│  [Retry]  [View Raw Data →]         │
└─────────────────────────────────────┘
```

---

## Status Color Semantics

| Status | Color | When to Use | User Action |
|--------|-------|-------------|-------------|
| 🟢 Certified | Green | Data validated, safe to use | Proceed |
| 🟡 Preliminary | Yellow | Data available but not validated | Use with caution |
| 🔴 Blocked | Red | Known issues, do not use | Wait or investigate |
| ⬜ Missing | Gray | Data not ingested | Run pipeline |

---

## Tier Behavior

### Basic Tier

Shows:
- Tier summary cards (latest week, symbol count)
- Basic availability (available/not available)
- Data Assets link

Does NOT show:
- Detailed week-by-week status
- Certification workflow
- Anomaly integration
- Dependency tracking

Message: "Detailed readiness tracking available in Intermediate tier"

### Intermediate Tier

Full functionality:
- Week-by-week readiness table
- Certification workflow
- Anomaly summary per week
- Dependency visualization
- Rolling window indicators

### Advanced Tier

Additional features:
- Certification audit trail
- Automated certification rules
- SLA tracking for freshness
- Alerts on staleness
