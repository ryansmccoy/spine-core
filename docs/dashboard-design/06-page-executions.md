# Page Spec: Executions

> Part of: [Dashboard Design](00-index.md)

## Page Identity

| Attribute | Value |
|-----------|-------|
| Route | `/dashboard/executions` |
| Primary Question | What ran, when, and what failed? |
| Secondary Questions | Why did it fail? Can I retry? What was affected? |
| Primary Persona | Platform Operator |
| Tier Required | Intermediate |

---

## Primary Question

> **What ran, when, and what failed?**

The operator needs to:
1. See chronological execution history
2. Quickly identify failures
3. Drill into failure context
4. Take action (retry, cancel)

---

## Page Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Executions                              [Auto-refresh: ON ▾]   │
├─────────────────────────────────────────────────────────────────┤
│  Time Range: [Last 24h ▾]  Status: [All ▾]  Pipeline: [All ▾]  │
├─────────────────────────────────────────────────────────────────┤
│  STATUS │ PIPELINE              │ STARTED      │ DURATION │ ⋮  │
│  ─────────────────────────────────────────────────────────────  │
│  ✓      │ finra.otc.ingest      │ 08:15 today  │ 45s      │    │
│  ❌      │ analytics.volume      │ 08:10 today  │ 12s      │ ⟳  │
│  ⏳      │ finra.nms.normalize   │ 08:05 today  │ running  │ ⏹  │
│  ✓      │ finra.otc.normalize   │ 07:45 today  │ 1m 22s   │    │
│  ✓      │ finra.otc.ingest      │ yesterday    │ 48s      │    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Metrics (List View)

| Column | Source | Notes |
|--------|--------|-------|
| `status` | Execution | pending / running / completed / failed |
| `pipeline` | Execution | Pipeline name |
| `started_at` | Execution | Relative or absolute time |
| `duration` | Execution | "running" if in progress |
| `rows_processed` | Execution | May be null |
| `trigger` | Execution | scheduled / manual / api |

---

## Execution Detail View

Route: `/dashboard/executions/:id`

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Executions                                                    │
│                                                                  │
│  Execution abc-123-def-456                                       │
│  ══════════════════════════════════════════════════════════════ │
│                                                                  │
│  ❌ FAILED                                                       │
│  Pipeline: finra.otc_transparency.ingest_week                   │
│  Started: 2025-01-04 08:10:15 UTC                               │
│  Duration: 12 seconds                                           │
│                                                                  │
│  [⟳ Retry]  [📋 Copy ID]                                        │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  [Summary]  [Parameters]  [Logs]  [Output]                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ERROR SUMMARY                                                   │
│  ─────────────                                                   │
│  HTTP 503: Service Temporarily Unavailable                      │
│                                                                  │
│  Request to https://api.finra.org/otc/weekly failed.            │
│  The upstream service returned a 503 error.                     │
│                                                                  │
│  SUGGESTED ACTIONS                                               │
│  ─────────────────                                               │
│  • Wait 5 minutes and retry                                     │
│  • Check FINRA service status: status.finra.org                 │
│  • If persistent, escalate to platform team                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Parameters Tab

```
┌─────────────────────────────────────────────────────────────────┐
│  PARAMETERS                                                      │
│  ──────────                                                      │
│                                                                  │
│  week_ending:   2025-12-22                                      │
│  tier:          OTC                                             │
│  dry_run:       false                                           │
│  force:         false                                           │
│                                                                  │
│  METADATA                                                        │
│  ────────                                                        │
│                                                                  │
│  capture_id:    cap_20250104_081015_abc123                      │
│  triggered_by:  schedule                                        │
│  trigger_time:  2025-01-04 08:10:00 UTC                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Logs Tab

```
┌─────────────────────────────────────────────────────────────────┐
│  EXECUTION LOGS                           [Download] [Copy]     │
│  ───────────────                                                 │
│                                                                  │
│  08:10:15.123 INFO  Starting pipeline execution                 │
│  08:10:15.145 INFO  Parameters validated                        │
│  08:10:15.200 INFO  Fetching from FINRA API...                  │
│  08:10:27.456 ERROR HTTP 503 from api.finra.org                 │
│  08:10:27.458 ERROR Response body: Service Temporarily...       │
│  08:10:27.460 INFO  Execution failed, cleaning up               │
│  08:10:27.512 INFO  Execution complete: FAILED                  │
│                                                                  │
│  ─── END OF LOGS ───                                            │
└─────────────────────────────────────────────────────────────────┘
```

### Output Tab (for successful runs)

```
┌─────────────────────────────────────────────────────────────────┐
│  EXECUTION OUTPUT                                                │
│  ────────────────                                                │
│                                                                  │
│  Rows Processed:  15,847                                        │
│  Symbols Added:   342                                           │
│  Weeks Updated:   1 (2025-12-22)                                │
│                                                                  │
│  OUTPUT SUMMARY                                                  │
│  ──────────────                                                  │
│  • Ingested OTC data for week ending 2025-12-22                 │
│  • Top symbol by volume: AAPL (2.3M shares)                     │
│  • New symbols added: 12                                        │
│                                                                  │
│  [View in Data Assets →]                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Default Filters

| Filter | Default | Options |
|--------|---------|---------|
| Time Range | Last 24h | Last hour, Last 24h, Last 7d, Last 30d, Custom |
| Status | All | All, Running, Completed, Failed |
| Pipeline | All | Dropdown of all pipeline names |
| Trigger | All | All, Scheduled, Manual, API |

---

## Filter Presets (Quick Filters)

| Preset | Filter Combination |
|--------|-------------------|
| "Recent Failures" | status=failed, time=24h |
| "Running Now" | status=running |
| "This Pipeline" | pipeline=:current |
| "Today's Runs" | time=today |

---

## Drill-Down Paths

| Element | Action | Destination |
|---------|--------|-------------|
| Execution row | Click | `/dashboard/executions/:id` |
| Pipeline name | Click | `/dashboard/pipelines/:name` |
| Retry button | Click | Confirm modal → new execution |
| Cancel button | Click | Confirm modal → cancel |
| View in Data Assets | Click | `/dashboard/assets?week=:week` |

---

## Actions

### Retry Execution

Available when: `status = failed`

```
┌───────────────────────────────────────────┐
│  Retry Execution?                         │
│                                           │
│  This will create a new execution with    │
│  the same parameters:                     │
│                                           │
│  Pipeline: finra.otc.ingest_week          │
│  week_ending: 2025-12-22                  │
│  tier: OTC                                │
│                                           │
│  ☐ Modify parameters before retry         │
│                                           │
│              [Cancel]  [Retry Now]        │
└───────────────────────────────────────────┘
```

### Cancel Execution

Available when: `status = running`

```
┌───────────────────────────────────────────┐
│  Cancel Execution?                        │
│                                           │
│  ⚠️ This may leave data in an            │
│  inconsistent state.                      │
│                                           │
│  Pipeline: finra.otc.ingest_week          │
│  Running for: 3m 45s                      │
│                                           │
│              [Keep Running]  [Cancel]     │
└───────────────────────────────────────────┘
```

---

## Status Indicators

| Status | Icon | Color | Meaning |
|--------|------|-------|---------|
| `pending` | ◯ | Gray | Queued, not started |
| `running` | ⏳ | Blue (animated) | In progress |
| `completed` | ✓ | Green | Succeeded |
| `failed` | ❌ | Red | Error occurred |
| `cancelled` | ⏹ | Gray | User cancelled |
| `dry_run` | 📋 | Blue | Validation only |

---

## Failure Context

### Error Classification

| Error Type | Icon | Suggested Action |
|------------|------|------------------|
| Transient (503, timeout) | 🔄 | Auto-retry or manual retry |
| Data issue (missing file) | 📁 | Check source availability |
| Config error (bad params) | ⚙️ | Review parameters |
| Dependency (missing prereq) | 🔗 | Run prerequisite first |
| Unknown | ❓ | Check logs, escalate |

### Suggested Actions

For known error patterns, show actionable suggestions:

```
ERROR: HTTP 503 from FINRA API
CLASSIFICATION: Transient - upstream service unavailable

SUGGESTED ACTIONS:
1. ⏰ Wait 5-10 minutes and retry (FINRA may be under maintenance)
2. 🔍 Check FINRA status page: https://status.finra.org
3. 📧 If persistent >1 hour, contact platform team
```

---

## Tier Behavior

### Basic Tier

This page is NOT available in Basic tier.

Show:
```
┌─────────────────────────────────────┐
│  📊 Execution History               │
│                                     │
│  Execution history is available     │
│  in the Intermediate tier.          │
│                                     │
│  Basic tier supports sync           │
│  execution with immediate results.  │
│                                     │
│  [Learn about tiers]                │
└─────────────────────────────────────┘
```

### Intermediate Tier

Full functionality as described.

### Advanced Tier

Additional features:
- SLA breach indicators
- Cost attribution
- Resource utilization graphs
- Comparison with baseline
