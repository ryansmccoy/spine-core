# Page Spec: Pipelines

> Part of: [Dashboard Design](00-index.md)

## Page Identity

| Attribute | Value |
|-----------|-------|
| Route | `/dashboard/pipelines` |
| Primary Question | What pipelines exist and can I run them? |
| Secondary Questions | What are the parameters? When did it last run? |
| Primary Persona | Platform Operator |
| Tier Required | Basic |

---

## Primary Question

> **What pipelines exist and can I run them?**

The operator needs to:
1. See all available pipelines
2. Understand what each does
3. Trigger a run with correct parameters

---

## Page Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Pipelines                                    [+ Run Pipeline]  │
├─────────────────────────────────────────────────────────────────┤
│  Filter: [All ▾] [Ingest ▾] [Compute ▾]    Search: [________]  │
├─────────────────────────────────────────────────────────────────┤
│  NAME                    │ TYPE    │ LAST RUN  │ STATUS │ ⋮    │
│  ─────────────────────────────────────────────────────────────  │
│  finra.otc.ingest_week   │ Ingest  │ 2h ago    │ ✓      │ [▶]  │
│  finra.otc.normalize     │ Ingest  │ 2h ago    │ ✓      │ [▶]  │
│  analytics.volume        │ Compute │ 1d ago    │ ✓      │ [▶]  │
│  backfill.otc_range      │ Backfill│ 7d ago    │ ✓      │ [▶]  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Metrics (List View)

| Column | Source | Notes |
|--------|--------|-------|
| `name` | Pipeline | Full qualified name |
| `description` | Pipeline | Truncated to 60 chars |
| `type` | Derived | ingest / normalize / compute / backfill |
| `last_run` | Latest execution | Relative time |
| `last_status` | Latest execution | ✓ / ❌ / ⏳ / — |
| `is_scheduled` | Schedule (Intermediate+) | ⏰ icon if scheduled |

---

## Pipeline Detail View

Route: `/dashboard/pipelines/:name`

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Pipelines                                                     │
│                                                                  │
│  finra.otc_transparency.ingest_week                             │
│  ══════════════════════════════════════════════════════════════ │
│  Ingest FINRA OTC weekly transparency data for a specific week. │
│                                                                  │
├───────────────────────────────────────────────────────────────── │
│  [Overview]  [Parameters]  [History]  [Schedule]                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  QUICK STATS                                                     │
│  ───────────                                                     │
│  Last Run: 2025-01-04 08:15 UTC (✓ completed in 45s)            │
│  Avg Duration: 52s (last 10 runs)                               │
│  Success Rate: 95% (last 30 days)                               │
│                                                                  │
│  [▶ Run Pipeline]                                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Parameters Tab

```
┌─────────────────────────────────────────────────────────────────┐
│  REQUIRED PARAMETERS                                             │
│  ───────────────────                                             │
│                                                                  │
│  week_ending    [2025-12-22    ] 📅                             │
│  Date (YYYY-MM-DD) - The week ending date to ingest             │
│                                                                  │
│  tier           [OTC          ▾]                                │
│  Enum - Data tier: OTC, NMS_TIER_1, NMS_TIER_2                  │
│                                                                  │
│  OPTIONAL PARAMETERS                                             │
│  ──────────────────                                              │
│                                                                  │
│  ☐ dry_run      false                                           │
│  Boolean - If true, validate without writing                    │
│                                                                  │
│  ☐ force        false                                           │
│  Boolean - If true, overwrite existing data                     │
│                                                                  │
│                                      [Cancel]  [▶ Run Pipeline]  │
└─────────────────────────────────────────────────────────────────┘
```

### History Tab (Intermediate+)

```
┌─────────────────────────────────────────────────────────────────┐
│  Execution History (last 20)                                     │
├─────────────────────────────────────────────────────────────────┤
│  EXECUTION ID   │ STARTED      │ DURATION │ STATUS  │ PARAMS   │
│  ────────────────────────────────────────────────────────────── │
│  abc123...      │ Jan 4, 08:15 │ 45s      │ ✓       │ [view]   │
│  def456...      │ Jan 3, 08:12 │ 52s      │ ✓       │ [view]   │
│  ghi789...      │ Jan 2, 08:18 │ 2m 15s   │ ❌       │ [view]   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Default Filters

| Filter | Default | Options |
|--------|---------|---------|
| Type | All | All, Ingest, Normalize, Compute, Backfill |
| Status | All | All, Has Failures, Never Run |
| Search | Empty | Text search on name and description |

---

## Drill-Down Paths

| Element | Action | Destination |
|---------|--------|-------------|
| Pipeline row | Click | `/dashboard/pipelines/:name` |
| Run button (list) | Click | Open run modal |
| Run button (detail) | Click | Scroll to parameters |
| Execution in history | Click | `/dashboard/executions/:id` |
| Schedule tab | Click | Schedule configuration |

---

## Run Pipeline Modal/Form

### Validation Rules

| Rule | Behavior |
|------|----------|
| Required param missing | Disable submit, highlight field |
| Invalid date format | Show inline error |
| Week in future | Warning (allow but flag) |
| Already running | Show "Pipeline already running" |
| Recent dry_run exists | Suggest: "Review dry run before real run?" |

### Confirmation Dialog (for destructive ops)

```
┌───────────────────────────────────────────┐
│  Confirm Pipeline Execution               │
│                                           │
│  You are about to run:                    │
│  finra.otc.ingest_week                    │
│                                           │
│  with force=true                          │
│                                           │
│  ⚠️ This will overwrite existing data    │
│  for week 2025-12-22.                     │
│                                           │
│           [Cancel]  [Confirm & Run]       │
└───────────────────────────────────────────┘
```

---

## Status Indicators

| Icon | Meaning | Color |
|------|---------|-------|
| ✓ | Last run succeeded | Green |
| ❌ | Last run failed | Red |
| ⏳ | Currently running | Blue/animated |
| — | Never run | Gray |
| ⏰ | Scheduled | Blue clock |
| ⚠️ | Overdue | Yellow |

---

## Failure States

### No Pipelines Registered

```
┌─────────────────────────────────────┐
│  📋 No Pipelines Found              │
│                                     │
│  No pipelines are registered in     │
│  the system.                        │
│                                     │
│  This usually means the backend     │
│  is not fully configured.           │
│                                     │
│  [Check System Settings]            │
└─────────────────────────────────────┘
```

### Pipeline Not Found (detail)

```
┌─────────────────────────────────────┐
│  ❌ Pipeline Not Found              │
│                                     │
│  Pipeline "foo.bar.baz" does not    │
│  exist or has been removed.         │
│                                     │
│  [← Back to Pipelines]              │
└─────────────────────────────────────┘
```

---

## Tier Behavior

### Basic Tier

Shows:
- Pipeline list with descriptions
- Pipeline detail with parameters
- Sync execution (wait for result)
- Last execution status

Does NOT show:
- Execution history tab
- Schedule tab
- Avg duration / success rate (needs history)

### Intermediate Tier

Shows:
- All of Basic
- Execution history tab (last 20 runs)
- Schedule tab (view and edit)
- Duration trends
- Success rate metrics

### Advanced Tier

Shows:
- All of Intermediate
- Dependency graph visualization
- Alert configuration
- SLA indicators
