# Dashboard Anti-Patterns

> Part of: [Dashboard Design](00-index.md)

## Purpose

This document explicitly lists bad dashboard ideas to avoid. Learn from the failures of countless enterprise dashboards.

---

## 1. "Tables Everywhere" Syndrome

### The Anti-Pattern

Every page is just a filterable table of entities:
- Pipelines table
- Executions table  
- Anomalies table
- Settings table

### Why It Fails

| Problem | Impact |
|---------|--------|
| No visual hierarchy | User can't find what's urgent |
| Equal weight to all rows | Critical issues buried in noise |
| Requires reading every row | Slow time-to-insight |
| No context between entities | User must mentally connect dots |
| Mobile/responsive nightmare | Tables don't scale down |

### Better Approach

- **Status-first views**: Show aggregate health before details
- **Visual encoding**: Color, size, position convey importance
- **Progressive disclosure**: Summary → List → Detail
- **Exception-based display**: Only show what needs attention

```
❌ BAD: A table of 50 pipelines sorted alphabetically

✅ GOOD: 
   "12 pipelines healthy"
   "1 pipeline failed" [highlighted, clickable]
   "2 pipelines running"
   [Expand to see full list]
```

---

## 2. Vanity Metrics

### The Anti-Pattern

Displaying impressive-looking numbers that don't inform action:

- "1,234,567 rows processed all time"
- "99.97% uptime"
- "Pipeline ran 4,521 times"

### Why It Fails

| Problem | Impact |
|---------|--------|
| Doesn't answer operator questions | Ignored after first view |
| Creates false confidence | "99% success" hides recent failures |
| Takes space from useful info | Cognitive load without value |
| Often misleading | Cumulative stats hide trends |

### Better Approach

Show metrics that **drive action**:

```
❌ BAD: "99.2% success rate all time"

✅ GOOD: "3 failures in last 24h (vs 0 yesterday)"
         ↳ This tells me something changed
```

| Vanity Metric | Actionable Alternative |
|---------------|----------------------|
| Total rows ever | Rows processed today vs expected |
| Uptime percentage | Current status + recent incidents |
| Total runs | Runs today, success rate trend |
| Data size | Data freshness, staleness |

---

## 3. Alert Fatigue Design

### The Anti-Pattern

- Everything is red/yellow/green
- Every row has a status icon
- Notifications for every event
- "Warning" threshold set too low

### Why It Fails

| Problem | Impact |
|---------|--------|
| Desensitization | Users ignore all alerts |
| Cry wolf effect | Real issues missed |
| Constant anxiety | Dashboard becomes stressful |
| No prioritization | Can't tell critical from minor |

### Better Approach

**Severity budget**: Only N things can be "red" at once

```
❌ BAD:
   🔴 Pipeline A - ran 5 min late
   🔴 Pipeline B - ran 5 min late
   🔴 Pipeline C - ran 5 min late
   🔴 Pipeline D - failed
   🔴 Pipeline E - ran 5 min late

✅ GOOD:
   🔴 1 Critical: Pipeline D failed [NEEDS ACTION]
   🟡 4 Warnings: Slight delays (within tolerance)
```

**Alert thresholds by consequence**:
- 🔴 **Critical**: Data consumers blocked, money at risk
- 🟡 **Warning**: Degraded but operational, needs attention
- ⚪ **Info**: Notable but not actionable

---

## 4. Configuration Overload

### The Anti-Pattern

- 50 settings on one page
- Every behavior is configurable
- No defaults, user must set everything
- Settings have no visible effect

### Why It Fails

| Problem | Impact |
|---------|--------|
| Analysis paralysis | Users don't know what to change |
| Wrong defaults | System broken until configured |
| Hidden consequences | Changing X breaks Y |
| Maintenance burden | Every setting needs docs |

### Better Approach

```
❌ BAD:
   [ ] Enable feature A
   [ ] Enable feature B
   [  ] Threshold for C (default: 0)
   [  ] Timeout for D (default: 0)
   [  ] Max retries (default: 0)
   ... 45 more options ...

✅ GOOD:
   Sensible defaults, working out of the box
   
   Advanced Settings [collapsed]
   └── Only show when user explicitly wants to tune
```

**Progressive disclosure for settings**:
1. **Level 1**: Works with defaults (most users)
2. **Level 2**: Common tweaks (10% of users)
3. **Level 3**: Advanced tuning (1% of users)

---

## 5. Dashboard as Report Generator

### The Anti-Pattern

Treating the dashboard as a BI tool:
- Heavy use of date range pickers
- Lots of aggregation options
- Export to PDF/Excel on every page
- Charts for everything

### Why It Fails

| Problem | Impact |
|---------|--------|
| Wrong use case | Operators need real-time, not reports |
| Slow page loads | Aggregations take time |
| Wrong audience | Analysts use Jupyter/SQL, not dashboards |
| Feature creep | Dashboard becomes bloated |

### Better Approach

| Use Case | Right Tool |
|----------|------------|
| What's happening now? | Dashboard (real-time) |
| What happened last quarter? | BI tool (Metabase, Tableau) |
| Deep data analysis | SQL / Jupyter |
| Audit trail | Dedicated audit log |

Dashboard should be **cockpit**, not **accounting ledger**.

---

## 6. "Show Everything" Default

### The Anti-Pattern

- Default view shows all data, all time
- No smart filtering
- User must manually filter every visit
- Assumption that more data = better

### Why It Fails

| Problem | Impact |
|---------|--------|
| Slow initial load | Bad first impression |
| Overwhelms new users | Don't know where to look |
| Buries recent/important | Yesterday's failure in page 50 |
| Wastes resources | Query all data when 1% is relevant |

### Better Approach

**Smart defaults**:

```
❌ BAD: Executions (all time) - 50,000 rows

✅ GOOD: Executions (last 24h) - 47 rows
         [Show more] [All time]
```

| Default | Reason |
|---------|--------|
| Last 24 hours | Recent is relevant |
| Failures first | Exceptions need attention |
| Current tier | User's likely focus |
| Top 20 | Scannable without scrolling |

---

## 7. Modal Hell

### The Anti-Pattern

- Every action opens a modal
- Modals inside modals
- Confirmation for non-destructive actions
- Long forms in modals

### Why It Fails

| Problem | Impact |
|---------|--------|
| Context switch | User loses place |
| Mobile unusable | Modals don't scale |
| Click fatigue | Extra clicks for simple actions |
| State management | What happens if modal fails? |

### Better Approach

| Action Type | UI Pattern |
|-------------|------------|
| View details | Inline expand or side panel |
| Quick edit | Inline editing |
| Destructive action | Confirmation modal (acceptable) |
| Complex form | Full page, not modal |

```
❌ BAD: Click "View" → Modal → Click "Logs" → Another Modal

✅ GOOD: Click row → Expands inline with tabs
         Or: Click row → Side panel slides in
```

---

## 8. Hiding Critical Information

### The Anti-Pattern

- Errors shown for 3 seconds then disappear
- Status only visible on drill-down
- Must click to see if there are problems
- No persistent indicators

### Why It Fails

| Problem | Impact |
|---------|--------|
| Missed issues | User wasn't looking at right moment |
| False confidence | "No alerts visible" ≠ "no problems" |
| Extra clicks | Must navigate to find issues |
| Bad mental model | User assumes dashboard shows problems |

### Better Approach

**Persistent error surfaces**:

```
❌ BAD: Toast notification → disappears after 5 seconds

✅ GOOD: Error banner stays until acknowledged
         Badge count on nav item
         Health indicator in header always visible
```

**Header health indicator**:
```
┌──────────────────────────────────────────────────────┐
│ Market Spine    [🔴]    [BASIC]    [User ▾]         │
│                  ↑                                    │
│           Always visible, click for details          │
└──────────────────────────────────────────────────────┘
```

---

## 9. Inconsistent Time References

### The Anti-Pattern

- Some timestamps in UTC, some local
- Relative time ("2 hours ago") without absolute option
- No timezone indicator
- Mixing "2025-01-04" and "Jan 4, 2025"

### Why It Fails

| Problem | Impact |
|---------|--------|
| Confusion in distributed teams | "When was 2pm?" |
| Incorrect debugging | Wrong time window investigated |
| Trust erosion | Users unsure of data |
| Audit failures | Can't prove exact times |

### Better Approach

| Rule | Implementation |
|------|----------------|
| Always show timezone | "08:15 UTC" or "08:15 EST" |
| Hover for absolute | Relative shows "2h ago", hover shows full ISO |
| Consistent format | ISO 8601 for machines, localized for display |
| User preference | Let user set preferred timezone |

```
✅ GOOD:
   Started: 2 hours ago
            ↳ Hover: "2025-01-04T08:15:00Z (UTC)"
```

---

## 10. No Empty States

### The Anti-Pattern

- Blank page when no data
- "No results" with no guidance
- Error states indistinguishable from empty states
- Loading states look like empty states

### Why It Fails

| Problem | Impact |
|---------|--------|
| User confusion | Is it broken or empty? |
| Dead end | User doesn't know what to do next |
| Bad first impression | New user sees blank dashboard |
| Missing context | Why is it empty? |

### Better Approach

Every state needs explicit design:

| State | Display |
|-------|---------|
| Loading | Skeleton + spinner, NOT blank |
| Empty (new user) | Welcome message + CTA |
| Empty (filtered) | "No results for filter X" + clear filter |
| Error | Error message + retry + help link |
| Partial error | Show what loaded, indicate what failed |

```
❌ BAD: [blank table]

✅ GOOD:
   ┌─────────────────────────────────────┐
   │  📊 No Executions Yet               │
   │                                     │
   │  Run your first pipeline to see     │
   │  execution history here.            │
   │                                     │
   │  [Go to Pipelines]                  │
   └─────────────────────────────────────┘
```

---

## Summary: Dashboard Design Principles

| Principle | Anti-Pattern to Avoid |
|-----------|----------------------|
| Status before details | Tables everywhere |
| Actionable metrics | Vanity metrics |
| Meaningful alerts | Alert fatigue |
| Sensible defaults | Configuration overload |
| Real-time focus | Report generator mentality |
| Smart filtering | Show everything default |
| Contextual actions | Modal hell |
| Persistent indicators | Hiding critical info |
| Consistent time | Timezone chaos |
| Explicit states | Blank/empty confusion |
