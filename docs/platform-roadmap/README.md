# Platform Roadmap

> **Purpose:** Comprehensive implementation plan for spine-core platform capabilities.
> **Scope:** Basic and Intermediate tier features for spine-core, framework, and orchestration.
> **Status:** Planning Phase

---

## Document Index

| Document | Purpose | Status |
|----------|---------|--------|
| [00-EXECUTIVE-SUMMARY.md](./00-EXECUTIVE-SUMMARY.md) | Overview and timeline | ✅ Complete |
| [01-GAP-ANALYSIS.md](./01-GAP-ANALYSIS.md) | Current state vs target state | ✅ Complete |
| [02-SOURCE-PROTOCOL.md](./02-SOURCE-PROTOCOL.md) | Unified data source abstraction | ✅ Complete |
| [03-ERROR-FRAMEWORK.md](./03-ERROR-FRAMEWORK.md) | Structured error handling | ✅ Complete |
| [04-DATABASE-ADAPTERS.md](./04-DATABASE-ADAPTERS.md) | PostgreSQL, DB2, SQLite adapters | ✅ Complete |
| [05-ALERTING-FRAMEWORK.md](./05-ALERTING-FRAMEWORK.md) | Slack, ServiceNow, Email channels | ✅ Complete |
| [06-SCHEDULER-SERVICE.md](./06-SCHEDULER-SERVICE.md) | Cron-based pipeline scheduling | ✅ Complete |
| [07-WORKFLOW-HISTORY.md](./07-WORKFLOW-HISTORY.md) | Run history and persistence | ✅ Complete |
| [08-SCHEMA-CHANGES.md](./08-SCHEMA-CHANGES.md) | Database migrations | ✅ Complete |
| [09-INTEGRATION-FLOW.md](./09-INTEGRATION-FLOW.md) | End-to-end data flow | ✅ Complete |
| [10-FINRA-EXAMPLE.md](./10-FINRA-EXAMPLE.md) | FINRA domain with new features | ✅ Complete |
| [11-IMPLEMENTATION-ORDER.md](./11-IMPLEMENTATION-ORDER.md) | Phased implementation plan | ✅ Complete |

---

## Quick Links

- **LLM Prompts:** [../llm-prompts/](../llm-prompts/) - Guidance for implementing features
- **Tier Comparison:** [../tier-comparison.md](../tier-comparison.md) - Feature matrix by tier
- **Anti-Patterns:** [../llm-prompts/ANTI_PATTERNS.md](../llm-prompts/ANTI_PATTERNS.md) - What NOT to do

---

## Design Principles

These documents follow the established patterns:

1. **Write Once** - Design for future extensibility, avoid rewrites
2. **Registry-Driven** - No if/elif factories, use registries
3. **Layering** - Domains > App > Core (minimize core changes)
4. **Capture ID Contract** - Every output has lineage
5. **Idempotency** - Same inputs → same outputs
6. **Quality Gates** - Validate before compute

> **Full Design Principles Reference:** [llm-prompts/reference/DESIGN_PRINCIPLES.md](../llm-prompts/reference/DESIGN_PRINCIPLES.md)

---

## Design Principles Compliance

Each document in this roadmap follows the 14 design principles. Key compliance:

| Document | Key Principles Applied |
|----------|----------------------|
| [02-SOURCE-PROTOCOL](./02-SOURCE-PROTOCOL.md) | Protocol-First (#2), Registry-Driven (#3), Errors as Values (#7) |
| [03-ERROR-FRAMEWORK](./03-ERROR-FRAMEWORK.md) | Errors as Values (#7), Observable (#13) |
| [04-DATABASE-ADAPTERS](./04-DATABASE-ADAPTERS.md) | Registry-Driven (#3), Progressive Enhancement (#11) |
| [05-ALERTING-FRAMEWORK](./05-ALERTING-FRAMEWORK.md) | Registry-Driven (#3), Write Once (#1) |
| [06-SCHEDULER-SERVICE](./06-SCHEDULER-SERVICE.md) | Immutability (#5), Separation of Concerns (#10) |
| [07-WORKFLOW-HISTORY](./07-WORKFLOW-HISTORY.md) | Observable (#13), Idempotency (#8) |

### Notable Pragmatic Exceptions

1. **SpineError mutability** - Exceptions use mutable `with_context()` for Python compatibility
2. **WorkflowRun state** - Run status updates in-place for performance; use events for tracking

---

## Tier Scope

| Tier | Database | API | Scheduling | Alerting |
|------|----------|-----|------------|----------|
| **Basic** | SQLite | CLI | Manual/cron | None |
| **Intermediate** | PostgreSQL | FastAPI | Scheduler service | Slack/Email |
| **Advanced** | PostgreSQL | FastAPI | + Celery | + ServiceNow |
| **Full** | PostgreSQL | FastAPI | + K8s CronJob | + PagerDuty |

---

## How to Use These Documents

### For Implementation

1. Read [00-EXECUTIVE-SUMMARY.md](./00-EXECUTIVE-SUMMARY.md) for overview
2. Review [01-GAP-ANALYSIS.md](./01-GAP-ANALYSIS.md) for current state
3. Follow [11-IMPLEMENTATION-ORDER.md](./11-IMPLEMENTATION-ORDER.md) for sequencing
4. Use specific docs (02-10) for detailed designs

### For LLM Sessions

Inject these documents as context when implementing features:

```
CONTEXT: Read docs/platform-roadmap/02-SOURCE-PROTOCOL.md

TASK: Implement FileSource adapter for CSV files
```

### For Code Review

Reference these documents when reviewing PRs to ensure alignment.
