# Page Spec: Global Overview

> Part of: [Dashboard Design](00-index.md)

## Page Identity

| Attribute | Value |
|-----------|-------|
| Route | `/dashboard` |
| Primary Question | Is the system healthy right now? |
| Secondary Questions | What broke? What's stale? What's next? |
| Primary Persona | Platform Operator |
| Tier Required | Basic |

---

## Primary Question

> **Is the system healthy right now?**

The operator opens this page first thing in the morning. Within 5 seconds, they should know:
- All green → move on with day
- Yellow/Red → investigate immediately

---

## Key Metrics

### Health Summary Card

| Metric | Source | Calculation |
|--------|--------|-------------|
| `overall_status` | Derived | worst(pipeline_health, data_freshness, queue_health) |
| `status_reason` | Derived | First critical issue description |

Display: Large colored circle with label
- 🟢 "All Systems Healthy"
- 🟡 "Warning: {reason}"
- 🔴 "Critical: {reason}"

### Pipeline Health Card

| Metric | Source | Calculation |
|--------|--------|-------------|
| `total_pipelines` | `/v1/pipelines` | count |
| `failed_24h` | `/v1/executions?status=failed&since=24h` | count |
| `success_rate_24h` | Derived | (succeeded / total) × 100 |
| `currently_running` | `/v1/executions?status=running` | count |

Display:
```
Pipelines
─────────
12 total   3 running   98% success (24h)
[1 failed] ← red if > 0
```

### Data Freshness Card

| Metric | Source | Calculation |
|--------|--------|-------------|
| `latest_week_otc` | `/v1/data/weeks?tier=OTC&limit=1` | week_ending |
| `latest_week_nms1` | `/v1/data/weeks?tier=NMS_TIER_1&limit=1` | week_ending |
| `latest_week_nms2` | `/v1/data/weeks?tier=NMS_TIER_2&limit=1` | week_ending |
| `days_since_update` | Derived | now - max(latest_week) |
| `is_stale` | Derived | days_since_update > threshold |

Display:
```
Data Freshness
──────────────
OTC: Week of 2025-12-22 ✓
NMS Tier 1: Week of 2025-12-22 ✓
NMS Tier 2: Week of 2025-12-15 ⚠ (7 days old)
```

### Recent Failures Card (if any)

| Metric | Source | Calculation |
|--------|--------|-------------|
| `failures` | `/v1/executions?status=failed&limit=5` | list |
| `failure.pipeline` | Execution | pipeline name |
| `failure.when` | Execution | relative time ("2h ago") |
| `failure.error_summary` | Execution | first line of error |

Display:
```
Recent Failures
───────────────
❌ finra.otc.ingest_week     2h ago   "HTTP 503 from FINRA"
❌ analytics.volume.compute  4h ago   "Missing dependency"
                                      [View All]
```

### Upcoming Runs Card (Intermediate+)

| Metric | Source | Calculation |
|--------|--------|-------------|
| `scheduled_runs` | `/v1/schedules/upcoming?limit=5` | list |
| `overdue_runs` | `/v1/schedules/overdue` | list |

Display:
```
Scheduled Runs
──────────────
⏰ finra.otc.ingest_week     in 2h
⏰ analytics.volume.compute  in 4h
⚠️ finra.nms.ingest_week    OVERDUE by 6h
```

---

## Default Filters

None - Overview shows everything relevant.

---

## Drill-Down Paths

| Element | Action | Destination |
|---------|--------|-------------|
| Failed execution | Click | `/dashboard/executions/:id` |
| Pipeline name | Click | `/dashboard/pipelines/:name` |
| "View All Failures" | Click | `/dashboard/executions?status=failed` |
| Data tier row | Click | `/dashboard/assets?tier=:tier` |
| Scheduled run | Click | `/dashboard/pipelines/:name` |

---

## Failure States

### Empty State: No Data Yet

```
┌─────────────────────────────────────┐
│  📊 No Data Yet                     │
│                                     │
│  Run your first pipeline to see     │
│  system health here.                │
│                                     │
│  [Go to Pipelines]                  │
└─────────────────────────────────────┘
```

### Error State: Cannot Load

```
┌─────────────────────────────────────┐
│  ⚠️ Cannot Load Dashboard          │
│                                     │
│  Unable to connect to backend API.  │
│  Status: Connection refused         │
│                                     │
│  [Retry]  [View Details]            │
└─────────────────────────────────────┘
```

### Partial State: Some Data Missing

Show available cards, indicate missing data:
```
[Pipeline Health: Loading...]
[Data Freshness: ✓ Loaded]
[Recent Failures: ⚠ Error loading]
```

---

## Status Color Semantics

### Green (Healthy)

| Condition | Meaning |
|-----------|---------|
| All pipelines succeeded in last 24h | No failures |
| Data freshness within threshold | Data is current |
| No overdue scheduled runs | Schedule is on track |
| No critical anomalies | Quality is good |

### Yellow (Warning)

| Condition | Meaning |
|-----------|---------|
| 1-2 failures in 24h but not recurring | Transient issues |
| Data is 1-2 days stale | May need attention |
| Scheduled run is slightly overdue | Minor delay |
| Non-critical anomalies exist | Quality needs review |

### Red (Critical)

| Condition | Meaning |
|-----------|---------|
| Multiple failures or same pipeline failing repeatedly | Systemic issue |
| Data is >3 days stale | Data consumers blocked |
| Scheduled run is >1 day overdue | Schedule broken |
| Critical anomalies detected | Data quality compromised |

---

## Refresh Behavior

| Trigger | Behavior |
|---------|----------|
| Page load | Fetch all cards |
| Every 60 seconds | Auto-refresh health summary |
| Every 5 minutes | Auto-refresh all cards |
| Manual refresh button | Fetch all cards immediately |
| Visibility change (tab focus) | Refresh if stale > 1 minute |

---

## Tier Behavior

### Basic Tier

Shows:
- Health summary
- Pipeline count and list link
- Data freshness
- Last execution status (sync only)

Does NOT show:
- Recent failures list (no history)
- Scheduled runs (no scheduling)
- Queue depth (no queues)

Message: "Upgrade to Intermediate for execution history and scheduling"

### Intermediate Tier

Shows:
- All of Basic
- Recent failures list with history
- Scheduled/overdue runs
- Queue depth indicators

### Advanced Tier

Shows:
- All of Intermediate
- Alert configuration shortcuts
- Trend sparklines
- SLA breach indicators
