# Implementation Roadmap

> Part of: [Dashboard Design](00-index.md)

## Overview

This roadmap prioritizes dashboard features by value and dependency. Each phase builds on the previous, and earlier phases should be fully stable before advancing.

---

## Phase 1: Operational Foundation (Must-Have)

**Goal**: Operators can manage the system day-to-day without CLI.

**Timeline**: 2-3 weeks

### Scope

| Page | Features | Priority |
|------|----------|----------|
| Overview | Health indicator, pipeline count, data freshness | P0 |
| Pipelines | List, detail, run with params | P0 |
| Assets | Tier tabs, week list, symbol table | P0 |
| Settings | Version, tier, connection status | P1 |

### Backend Requirements

| Endpoint | Status | Action |
|----------|--------|--------|
| `GET /health` | ✅ Exists | Use as-is |
| `GET /v1/capabilities` | ✅ Exists | Use as-is |
| `GET /v1/pipelines` | ✅ Exists | Use as-is |
| `GET /v1/pipelines/{name}` | ✅ Exists | Use as-is |
| `POST /v1/pipelines/{name}/run` | ✅ Exists | Use as-is |
| `GET /v1/data/weeks` | ✅ Exists | Use as-is |
| `GET /v1/data/symbols` | ✅ Exists | Use as-is |
| `GET /v1/ops/storage` | ✅ Exists | Use as-is |

### Frontend Work

1. **SpineClient integration** (done)
   - Typed API client
   - Error handling
   - Capability detection

2. **Overview page redesign**
   - Health summary card
   - Pipeline count card
   - Data freshness cards (per tier)
   - Basic empty states

3. **Pipelines page improvements**
   - Parameter form generation from schema
   - Validation before submit
   - Success/failure feedback

4. **Assets page completion**
   - Tier tabs working
   - Week list with drill-down
   - Symbol table with search
   - Sample data preview

### Exit Criteria

- [ ] User can view system health
- [ ] User can run any pipeline with parameters
- [ ] User can browse all available data
- [ ] Empty states and error states handled
- [ ] Works on Basic tier without crashes

---

## Phase 2: Observability (Should-Have)

**Goal**: Operators can see what happened and debug failures.

**Timeline**: 3-4 weeks

### Scope

| Page | Features | Priority |
|------|----------|----------|
| Executions | List, filter, detail, logs | P0 |
| Overview | Recent failures, running count | P0 |
| Pipelines | History tab, last run status | P1 |
| Readiness | Week-by-week status | P1 |

### Backend Requirements (All New)

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/executions` | List executions with filters |
| `GET /v1/executions/{id}` | Execution detail |
| `GET /v1/executions/{id}/logs` | Execution logs |
| `POST /v1/executions/{id}/retry` | Retry failed |
| `POST /v1/executions/{id}/cancel` | Cancel running |
| `GET /v1/data/readiness` | Certification status |

### Frontend Work

1. **Executions page (new)**
   - Execution list with filters
   - Status icons and color coding
   - Relative timestamps with hover
   - Pagination/infinite scroll

2. **Execution detail (new)**
   - Summary header
   - Parameters tab
   - Logs tab with syntax highlighting
   - Error classification and suggested actions
   - Retry/cancel buttons

3. **Overview enhancements**
   - Recent failures card
   - Running executions count
   - Link to executions page

4. **Pipeline enhancements**
   - History tab (last N runs)
   - Last run indicator in list
   - Duration trends

5. **Readiness page (new)**
   - Basic version for Intermediate
   - Week table with status badges
   - Anomaly count integration

### Exit Criteria

- [ ] User can see all past executions
- [ ] User can view logs for any execution
- [ ] User can retry failed executions
- [ ] User can see data certification status
- [ ] Failures surfaced prominently

---

## Phase 3: Quality & Scheduling (Nice-to-Have)

**Goal**: Proactive quality management and automated operations.

**Timeline**: 4-5 weeks

### Scope

| Page | Features | Priority |
|------|----------|----------|
| Quality | Anomaly list, acknowledge flow | P0 |
| Pipelines | Schedule tab, cron editor | P1 |
| Overview | Scheduled/overdue runs | P1 |
| Readiness | Certification workflow | P2 |

### Backend Requirements (All New)

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/quality/anomalies` | List anomalies |
| `GET /v1/quality/anomalies/{id}` | Anomaly detail |
| `POST /v1/quality/anomalies/{id}/ack` | Acknowledge |
| `GET /v1/quality/rules` | Detection rules |
| `GET /v1/schedules` | List schedules |
| `GET /v1/schedules/{pipeline}` | Pipeline schedule |
| `PUT /v1/schedules/{pipeline}` | Update schedule |
| `POST /v1/data/readiness/certify` | Certify data |
| `POST /v1/data/readiness/block` | Block data |

### Frontend Work

1. **Quality page (new)**
   - Anomaly summary cards
   - Anomaly list with severity filter
   - Anomaly detail panel
   - Acknowledge workflow

2. **Scheduling (new)**
   - Schedule tab in pipeline detail
   - Cron expression builder
   - Next run preview
   - Enable/disable toggle

3. **Overview enhancements**
   - Scheduled runs card
   - Overdue runs warning

4. **Readiness enhancements**
   - Certify button with confirmation
   - Block button with reason
   - Audit trail display

### Exit Criteria

- [ ] User can view all detected anomalies
- [ ] User can acknowledge anomalies
- [ ] User can set pipeline schedules
- [ ] User can certify/block data
- [ ] Overdue runs surfaced

---

## Phase 4: Advanced Insights (Future)

**Goal**: Deep operational intelligence for enterprise use.

**Timeline**: 6+ weeks

### Scope

| Feature | Description |
|---------|-------------|
| Execution timeline | Gantt-style visualization |
| DAG view | Pipeline dependency graph |
| Capture lineage | Source → output tracking |
| Diff view | Compare captures/runs |
| Custom alerting | User-defined alert rules |
| Webhooks | External integrations |
| Multi-tenant | User/team management |

### Backend Requirements

| Endpoint Group | Purpose |
|----------------|---------|
| `/v1/data/lineage/*` | Lineage tracking |
| `/v1/data/diff/*` | Capture comparison |
| `/v1/alerts/*` | Alert management |
| `/v1/webhooks/*` | Webhook CRUD |
| `/v1/users/*` | User management |
| `/v1/audit/*` | Audit log access |

### Frontend Work

1. **Timeline visualization**
   - Horizontal Gantt chart
   - Zoom/pan controls
   - Execution bar colors

2. **DAG visualization**
   - Node-link diagram
   - Status indicators on nodes
   - Click to navigate

3. **Lineage page**
   - Source-to-output flow
   - Capture ID tracking
   - Impact analysis

4. **Alerting configuration**
   - Rule builder UI
   - Test alert function
   - Alert history

5. **User management**
   - User list (Advanced tier)
   - Role assignment
   - Audit log viewer

---

## Phase Summary

| Phase | Tier | Time | Key Deliverable |
|-------|------|------|-----------------|
| 1 | Basic | 2-3 wk | Run pipelines, browse data |
| 2 | Intermediate | 3-4 wk | Debug failures, track execution |
| 3 | Intermediate | 4-5 wk | Quality management, scheduling |
| 4 | Advanced | 6+ wk | Enterprise observability |

---

## Success Metrics

### Phase 1

| Metric | Target |
|--------|--------|
| Time to run a pipeline | < 30 seconds |
| Time to find latest data | < 10 seconds |
| Error rate on pipeline runs | < 1% UI errors |
| Page load time | < 2 seconds |

### Phase 2

| Metric | Target |
|--------|--------|
| Time to find failure cause | < 2 minutes |
| Retry success rate | > 80% (for transient errors) |
| Execution history load time | < 3 seconds |

### Phase 3

| Metric | Target |
|--------|--------|
| Anomaly detection to ack | < 4 hours |
| Schedule adherence | > 95% on-time |
| Certification coverage | 100% of production data |

### Phase 4

| Metric | Target |
|--------|--------|
| Lineage query time | < 5 seconds |
| Alert to notification | < 1 minute |
| Audit log availability | 100% |

---

## Dependencies

```
Phase 1 ─────────────► Phase 2 ─────────────► Phase 3
   │                      │                      │
   │                      │                      │
   ▼                      ▼                      ▼
 Basic API            Executions API         Quality API
 (exists)             (build)                (build)
                                                 │
                                                 ▼
                                            Phase 4
                                                │
                                                ▼
                                          Advanced API
                                            (build)
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Backend delays | Phase 1 works with existing API |
| Scope creep | Strict phase boundaries |
| Performance issues | Load testing each phase |
| User confusion | User testing after Phase 1 |
| Tier upgrade path unclear | Design tier comparison UI early |
