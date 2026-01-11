# Information Architecture

> Part of: [Dashboard Design](00-index.md)

## Dashboard Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                        GLOBAL HEADER                             │
│  [Logo] Market Spine    [Health: ●]    [Tier: Basic]   [User ▾] │
├─────────────┬───────────────────────────────────────────────────┤
│  NAVIGATION │                 CONTENT AREA                       │
│             │                                                     │
│  ┌────────┐ │  ┌─────────────────────────────────────────────┐   │
│  │Overview│◄├──┤ Primary viewport (single responsibility)    │   │
│  └────────┘ │  └─────────────────────────────────────────────┘   │
│             │                                                     │
│  OPERATIONS │                                                     │
│  ┌────────┐ │                                                     │
│  │Pipeline│ │                                                     │
│  └────────┘ │                                                     │
│  ┌────────┐ │                                                     │
│  │Executi-│ │                                                     │
│  │ons     │ │                                                     │
│  └────────┘ │                                                     │
│             │                                                     │
│  DATA       │                                                     │
│  ┌────────┐ │                                                     │
│  │Readine-│ │                                                     │
│  │ss      │ │                                                     │
│  └────────┘ │                                                     │
│  ┌────────┐ │                                                     │
│  │Quality │ │                                                     │
│  └────────┘ │                                                     │
│  ┌────────┐ │                                                     │
│  │Assets  │ │                                                     │
│  └────────┘ │                                                     │
│             │                                                     │
│  SYSTEM     │                                                     │
│  ┌────────┐ │                                                     │
│  │Settings│ │                                                     │
│  └────────┘ │                                                     │
└─────────────┴───────────────────────────────────────────────────┘
```

---

## Page Inventory

| Page | Primary Question | Persona | Tier Required |
|------|------------------|---------|---------------|
| Overview | Is the system healthy? | Operator | Basic |
| Pipelines | What pipelines exist and can I run them? | Operator | Basic |
| Executions | What ran, when, and what failed? | Operator | Intermediate |
| Data Readiness | Is data safe to use? | Quant | Basic+ |
| Quality | What anomalies exist? | Quant | Intermediate |
| Assets | What data do we have? | All | Basic |
| Settings | How is the system configured? | Operator | Basic |

---

## Why Each Page Exists

### Overview

**Purpose**: Single-glance system health assessment

**Replaces**:
- SSH into server and run health checks
- Checking multiple monitoring dashboards
- Asking "is everything okay?" in Slack

**What it shows**:
- Aggregate health indicator
- Recent failures (last 24h)
- Data freshness summary
- Upcoming/overdue runs

**What it does NOT show**:
- Historical trends (go to Executions)
- Individual pipeline details (go to Pipelines)
- Full failure logs (go to Execution detail)

---

### Pipelines

**Purpose**: Pipeline catalog and manual trigger interface

**Replaces**:
- CLI `spine pipelines list`
- Reading pipeline code to understand parameters
- Slack asking "what's the command to run X?"

**What it shows**:
- All registered pipelines with descriptions
- Required and optional parameters
- Last run status per pipeline
- Quick trigger with parameter form

**What it does NOT show**:
- Execution history (go to Executions)
- Output data (go to Assets)
- Scheduling configuration (Intermediate tier)

---

### Executions

**Purpose**: Audit trail and failure debugging

**Replaces**:
- Grepping log files
- SQL queries against execution tables
- "What happened to the 3am job?"

**What it shows**:
- Chronological execution list with filters
- Duration, status, error summaries
- Drill-down to logs and params
- Retry/cancel actions

**What it does NOT show**:
- Pipeline configuration (go to Pipelines)
- Data output (go to Assets)
- System metrics (go to Settings/Metrics)

---

### Data Readiness

**Purpose**: Trust signal for data consumers

**Replaces**:
- Manual SQL checks for data completeness
- Asking data team "can I use this week's data?"
- Mental tracking of what's been validated

**What it shows**:
- Tier-by-tier freshness summary
- Certification status (certified/preliminary/blocked)
- Completeness indicators (X/Y symbols, N/M weeks)
- Dependencies and staleness warnings

**What it does NOT show**:
- How data was produced (go to Executions)
- Raw data values (go to Assets)
- Quality issues detail (go to Quality)

---

### Quality

**Purpose**: Anomaly detection and investigation

**Replaces**:
- Manual data audits
- "This number looks wrong" investigations
- Post-hoc discovery of data issues

**What it shows**:
- Anomaly list with severity
- Affected data ranges
- Detection rules and thresholds
- Acknowledgement workflow

**What it does NOT show**:
- Normal data (only anomalies)
- How to fix (provides investigation context)
- Historical trends of metrics

---

### Assets

**Purpose**: Data inventory and exploration

**Replaces**:
- SQL `SELECT * FROM ... LIMIT 10`
- "What symbols do we have for week X?"
- File browser for data directories

**What it shows**:
- Tier breakdown (OTC, NMS_T1, NMS_T2)
- Week inventory per tier
- Symbol lists with volume ranking
- Sample data preview

**What it does NOT show**:
- Full data export (use API)
- Derived analytics (go to specific calcs)
- Data quality (go to Quality)

---

### Settings

**Purpose**: System configuration and diagnostics

**Replaces**:
- Config file editing
- Environment variable inspection
- "What version are we running?"

**What it shows**:
- API version and tier
- Connection status
- Storage statistics
- Configuration options (where applicable)

**What it does NOT show**:
- Operational data (go to other pages)
- User management (Advanced tier)
- Billing (external system)

---

## Navigation Principles

### Depth Limit: 3 Levels

```
Level 1: Page (Overview, Pipelines, ...)
Level 2: Entity (Pipeline detail, Execution detail)
Level 3: Sub-entity (Execution logs, Parameter history)
```

No deeper than 3 levels. If needed, open in panel/modal.

### Breadcrumb Pattern

```
Pipelines > finra.otc_transparency.ingest_week > Run #abc123
```

Always show path back to parent.

### Cross-Linking

| From | To | Trigger |
|------|-----|---------|
| Overview failure card | Execution detail | Click failure |
| Pipeline row | Pipeline detail | Click row |
| Pipeline detail | Latest execution | Click "last run" |
| Execution row | Execution detail | Click row |
| Execution detail | Pipeline detail | Click pipeline name |
| Readiness row | Related executions | Click "show runs" |
| Quality anomaly | Affected data | Click "view data" |

### URL Structure

```
/dashboard                    # Overview
/dashboard/pipelines          # Pipeline list
/dashboard/pipelines/:name    # Pipeline detail
/dashboard/executions         # Execution list
/dashboard/executions/:id     # Execution detail
/dashboard/readiness          # Data readiness
/dashboard/quality            # Quality/anomalies
/dashboard/assets             # Data assets
/dashboard/settings           # Settings
```

---

## Information Density Guidelines

### Overview Page

- **High density**: Many signals, low detail
- Cards with numbers, icons, status
- No tables on overview

### List Pages (Pipelines, Executions)

- **Medium density**: Scannable tables
- 5-8 columns maximum
- Status icons, not text
- Sortable and filterable

### Detail Pages

- **Lower density**: Focused context
- Header with key facts
- Tabbed sections for depth
- Logs/output in monospace

### Action Modals

- **Minimal density**: Single purpose
- One primary action
- Clear cancel path
- Parameter validation inline
