# Executive Summary

> **Purpose:** High-level overview of platform roadmap for Basic and Intermediate tiers.
> **Audience:** Architects, developers, project managers
> **Last Updated:** 2026-01-11

---

## Vision

Build a **production-ready data pipeline framework** that:

1. **Works today** - SQLite for development, PostgreSQL for production
2. **Scales tomorrow** - Add DB2, cloud storage, distributed execution later
3. **Never rewrites** - Abstractions designed for extension, not replacement

> **Design Principles:** This roadmap follows the 14 design principles in
> [DESIGN_PRINCIPLES.md](../llm-prompts/reference/DESIGN_PRINCIPLES.md).
> Key principles applied: Write Once (#1), Protocol-First (#2), Registry-Driven (#3).

---

## What We're Building

### Phase 1: Foundation (Basic Tier)

| Component | Description | Priority |
|-----------|-------------|----------|
| **Unified Source Protocol** | Common interface for File/API/DB sources | HIGH |
| **Structured Error Types** | `SourceError`, `TransformError`, `LoadError` | HIGH |
| **Result Envelope** | Consistent success/failure with metrics | HIGH |
| **File Source Adapter** | Read CSV, PSV, JSON, Parquet | MEDIUM |
| **Database Source Adapter** | Read from SQLite/PostgreSQL/DB2 | MEDIUM |
| **Simple Retry** | Retry N times with fixed delay | LOW |

### Phase 2: Operations (Intermediate Tier)

| Component | Description | Priority |
|-----------|-------------|----------|
| **Scheduler Service** | Cron-based pipeline execution | HIGH |
| **Schedule Registry** | `@register_schedule("0 6 * * 1-5")` | HIGH |
| **Workflow Run History** | Persist and query workflow executions | HIGH |
| **Alerting Framework** | Slack, Email, ServiceNow channels | MEDIUM |
| **API Source Adapter** | HTTP client with auth/pagination | MEDIUM |
| **PostgreSQL Adapter** | Production database support | MEDIUM |
| **DB2 Adapter** | Enterprise database support | MEDIUM |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (trading-desktop)                         │
│                              React + TypeScript                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ HTTP/REST
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        API LAYER (market-spine-{tier})                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  /executions│  │  /workflows │  │  /schedules │  │   /alerts   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ Dispatcher
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATION (spine.orchestration)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Workflows  │  │  Scheduler  │  │   Alerter   │  │  Run History│        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ Pipeline Registry
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FRAMEWORK (spine.framework)                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Dispatcher │  │  Registry   │  │   Sources   │  │    Errors   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ Source Protocol
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SOURCES (spine.framework.sources)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ FileSource  │  │ HttpSource  │  │ SQLiteSource│  │PostgreSource│        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│  ┌─────────────┐                                                            │
│  │  DB2Source  │                                                            │
│  └─────────────┘                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ Domain Logic
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DOMAINS (spine.domains)                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │    FINRA    │  │ Market Data │  │  Reference  │                         │
│  │  OTC Trans  │  │Alpha Vantage│  │  Calendar   │                         │
│  └─────────────┘  └─────────────┘  └─────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ Core Primitives
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CORE (spine.core)                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Manifest   │  │   Quality   │  │   Rejects   │  │  Execution  │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ Storage
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DATABASE (spine.core.storage)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │   SQLite    │  │ PostgreSQL  │  │     DB2     │                         │
│  │   (Basic)   │  │(Intermediate│  │ (Enterprise)│                         │
│  └─────────────┘  └─────────────┘  └─────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Database Strategy

### Current State
- **Basic tier:** SQLite for development and testing
- **All tests:** Run against SQLite

### Target State
- **Basic tier:** SQLite (unchanged)
- **Intermediate tier:** PostgreSQL for production
- **Enterprise option:** DB2 for legacy integration

### Migration Path
```
SQLite (dev/test) → PostgreSQL (staging/prod) → DB2 (enterprise)
         ↑                    ↑                        ↑
    Same schema          Same schema             Same schema
    Same queries         Minor dialect           DB2 dialect
```

---

## Timeline

### Week 1-2: Foundation
- [ ] Unified Source Protocol
- [ ] Structured Error Types
- [ ] Result Envelope
- [ ] Database Adapter Protocol

### Week 3-4: Sources
- [ ] FileSource (CSV, PSV, JSON, Parquet)
- [ ] SQLiteSource (with pagination)
- [ ] PostgreSQLSource
- [ ] DB2Source

### Week 5-6: Orchestration
- [ ] Simplified Workflow
- [ ] Workflow Run History
- [ ] Schedule Registry

### Week 7-8: Operations
- [ ] Scheduler Service
- [ ] Alerting Framework
- [ ] Slack/Email Channels

### Week 9-10: Integration
- [ ] FINRA example with new features
- [ ] API endpoints for schedules/alerts
- [ ] Frontend integration

---

## Success Criteria

### Basic Tier
- [ ] All existing tests pass with no changes
- [ ] FileSource works with FINRA PSV files
- [ ] SQLiteSource works for cross-table reads
- [ ] Error types provide actionable messages
- [ ] Result envelope used by all pipelines

### Intermediate Tier
- [ ] PostgreSQL works in Docker Compose
- [ ] Scheduler runs pipelines on cron
- [ ] Alerts fire to Slack on failure
- [ ] Run history queryable via API
- [ ] FINRA weekly refresh runs automatically

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing tests | HIGH | Run full test suite before/after each change |
| SQLite/PostgreSQL dialect differences | MEDIUM | Abstract SQL generation, test both |
| DB2 driver availability | LOW | Make DB2 adapter optional, test with mock |
| Scheduler reliability | MEDIUM | Use proven library (APScheduler), add monitoring |
| Alert fatigue | LOW | Rate limit alerts, add severity filtering |

---

## Related Documents

- [01-GAP-ANALYSIS.md](./01-GAP-ANALYSIS.md) - Detailed gap analysis
- [11-IMPLEMENTATION-ORDER.md](./11-IMPLEMENTATION-ORDER.md) - Implementation sequence
- [tier-comparison.md](../tier-comparison.md) - Feature matrix
- [CONTEXT.md](../llm-prompts/CONTEXT.md) - Repository context
