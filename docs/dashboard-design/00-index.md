# Market Spine Dashboard Design

> Version: 1.0  
> Date: 2026-01-04  
> Status: **DESIGN SPECIFICATION**

## Document Index

This design specification is split across multiple files for maintainability:

| File | Content |
|------|---------|
| [01-overview.md](01-overview.md) | System architecture overview |
| [02-personas.md](02-personas.md) | Operator personas and needs |
| [03-information-architecture.md](03-information-architecture.md) | Dashboard hierarchy and navigation |
| [04-page-global-overview.md](04-page-global-overview.md) | Global Overview page spec |
| [05-page-pipelines.md](05-page-pipelines.md) | Pipelines page spec |
| [06-page-executions.md](06-page-executions.md) | Executions page spec |
| [07-page-data-readiness.md](07-page-data-readiness.md) | Data Readiness page spec |
| [08-page-quality.md](08-page-quality.md) | Quality & Anomalies page spec |
| [09-page-assets.md](09-page-assets.md) | Data Assets page spec |
| [10-page-settings.md](10-page-settings.md) | Settings page spec |
| [11-execution-visualization.md](11-execution-visualization.md) | Timeline and DAG visualization |
| [12-tier-behavior.md](12-tier-behavior.md) | Tier-aware UI patterns |
| [13-api-contracts.md](13-api-contracts.md) | API contract mapping |
| [14-anti-patterns.md](14-anti-patterns.md) | Anti-patterns to avoid |
| [15-implementation-roadmap.md](15-implementation-roadmap.md) | Phased implementation plan |

---

## Core Design Principle

Every dashboard screen must answer at least ONE of these questions:

1. **Is the system healthy right now?**
2. **What broke most recently, and why?**
3. **Is data safe to use for trading / research?**
4. **What changed since yesterday?**
5. **What do I need to do next?**
6. **What will break if I do nothing?**

If a screen does not answer at least one of these, it should not exist.

---

## Why This Is NOT a CRUD App

| CRUD App Pattern | Control Plane Pattern |
|------------------|----------------------|
| Entity listing with pagination | Status-first views with anomalies surfaced |
| Create/Edit/Delete forms | Pipeline triggers with parameter validation |
| Detail pages per record | Execution timelines with dependency context |
| Filter by any field | Filter by operational state (failed, stale, blocked) |
| Equal visual weight to all records | Visual hierarchy by urgency and freshness |
| Success is default assumption | Failure is the expected interesting state |
| User creates data | System creates data; user monitors and intervenes |

The dashboard is a **cockpit**, not a **filing cabinet**.
