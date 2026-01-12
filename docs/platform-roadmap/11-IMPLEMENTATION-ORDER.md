# Implementation Order

> **Purpose:** Phased implementation plan with dependencies and timeline.
> **Tier:** All
> **Last Updated:** 2026-01-11

---

## Overview

This document outlines the implementation order for all platform-roadmap features. Each phase builds on the previous, minimizing rework and ensuring stable foundations.

**Total Estimated Duration:** 10 weeks

---

## Phase 0: Preparation (Week 1)

### Goals
- Validate designs with stakeholders
- Set up development environment
- Create test infrastructure

### Tasks

| Task | Description | Time |
|------|-------------|------|
| Review designs | Stakeholder review of all roadmap docs | 2 days |
| Dev environment | Docker compose for PostgreSQL, test DB2 | 1 day |
| Test framework | Pytest fixtures for database adapters | 1 day |
| CI/CD setup | GitHub Actions for new modules | 1 day |

### Deliverables
- Approved designs
- Docker compose with PostgreSQL
- Test fixtures for adapters
- CI pipeline updated

---

## Phase 1: Core Infrastructure (Week 2-3)

### Dependencies
- Phase 0 complete

### Order

```
1. spine.core.errors (no dependencies)
   ↓
2. spine.core.storage (depends on errors)
   ↓
3. Migrations (depends on storage)
```

### Week 2: Error Framework

| Task | File | Time |
|------|------|------|
| Error types | `spine/core/errors.py` | 1 day |
| Error categories | ErrorCategory enum | 0.5 day |
| Error context | ErrorContext dataclass | 0.5 day |
| Specific errors | SourceError, TransformError, etc. | 1 day |
| Tests | `tests/core/test_errors.py` | 1 day |
| Integration | Update existing code to use new errors | 1 day |

### Week 3: Storage Layer

| Task | File | Time |
|------|------|------|
| Base types | `spine/core/storage/types.py` | 1 day |
| SQLite adapter | `spine/core/storage/sqlite.py` | 1 day |
| PostgreSQL adapter | `spine/core/storage/postgres.py` | 1.5 days |
| DB2 adapter | `spine/core/storage/db2.py` | 1.5 days |
| Dialect helpers | `spine/core/storage/dialect.py` | 0.5 day |
| Tests | `tests/core/storage/` | 1 day |
| Migration runner | `spine/core/storage/migrations.py` | 0.5 day |

### Deliverables
- `spine.core.errors` module with all error types
- `spine.core.storage` module with 3 adapters
- 90%+ test coverage on new code
- Migration runner for schema changes

---

## Phase 2: Framework Layer (Week 4-5)

### Dependencies
- Phase 1 complete (errors, storage)

### Order

```
1. spine.framework.sources (depends on errors)
   ↓
2. spine.framework.alerts (depends on errors)
   ↓
3. Update existing pipelines (depends on sources)
```

### Week 4: Source Protocol

| Task | File | Time |
|------|------|------|
| Source protocol | `spine/framework/sources/protocol.py` | 1 day |
| Source result | `spine/framework/sources/result.py` | 0.5 day |
| File source | `spine/framework/sources/file.py` | 1 day |
| HTTP source | `spine/framework/sources/http.py` | 1 day |
| Database source | `spine/framework/sources/database.py` | 1 day |
| Source registry | `spine/framework/sources/registry.py` | 0.5 day |
| Tests | `tests/framework/sources/` | 1 day |

### Week 5: Alerting Framework

| Task | File | Time |
|------|------|------|
| Alert types | `spine/framework/alerts/types.py` | 0.5 day |
| Slack channel | `spine/framework/alerts/slack.py` | 1 day |
| Email channel | `spine/framework/alerts/email.py` | 1 day |
| ServiceNow channel | `spine/framework/alerts/servicenow.py` | 1 day |
| Alert router | `spine/framework/alerts/router.py` | 0.5 day |
| Throttling | `spine/framework/alerts/throttle.py` | 0.5 day |
| Tests | `tests/framework/alerts/` | 0.5 day |

### Deliverables
- `spine.framework.sources` module with 3 source types
- `spine.framework.alerts` module with 3 channels
- FINRA source updated to use new protocol

---

## Phase 3: Orchestration Layer (Week 6-7)

### Dependencies
- Phase 2 complete (sources, alerts)

### Order

```
1. spine.orchestration.history (depends on storage)
   ↓
2. spine.orchestration.scheduler (depends on storage)
   ↓
3. Integrate with WorkflowRunner (depends on history)
```

### Week 6: Workflow History

| Task | File | Time |
|------|------|------|
| History types | `spine/orchestration/history/types.py` | 0.5 day |
| History store | `spine/orchestration/history/store.py` | 1.5 days |
| History tracker | `spine/orchestration/history/tracker.py` | 1 day |
| Database schema | `migrations/intermediate/` | 0.5 day |
| Tests | `tests/orchestration/history/` | 1 day |
| WorkflowRunner integration | Update runner to use tracker | 1 day |

### Week 7: Scheduler Service

| Task | File | Time |
|------|------|------|
| Scheduler types | `spine/orchestration/scheduler/types.py` | 0.5 day |
| Scheduler service | `spine/orchestration/scheduler/service.py` | 2 days |
| Schedule loader | `spine/orchestration/scheduler/loader.py` | 0.5 day |
| Database schema | `migrations/intermediate/` | 0.5 day |
| Tests | `tests/orchestration/scheduler/` | 1 day |
| FINRA schedules | `config/schedules/finra.yaml` | 0.5 day |

### Deliverables
- `spine.orchestration.history` module
- `spine.orchestration.scheduler` module
- WorkflowRunner with history tracking
- FINRA schedule configuration

---

## Phase 4: API Layer (Week 8)

### Dependencies
- Phase 3 complete (history, scheduler)

### Tasks

| Task | File | Time |
|------|------|------|
| Pipeline endpoints | `spine/api/pipelines.py` | 1 day |
| History endpoints | `spine/api/history.py` | 1 day |
| Scheduler endpoints | `spine/api/scheduler.py` | 1 day |
| FINRA endpoints | `spine/api/finra.py` | 1 day |
| OpenAPI docs | Auto-generated | 0.5 day |
| Integration tests | `tests/api/` | 1 day |

### Deliverables
- All API endpoints implemented
- OpenAPI documentation
- Postman collection for testing

---

## Phase 5: Domain Integration (Week 9)

### Dependencies
- Phase 4 complete (API)

### Tasks

| Task | File | Time |
|------|------|------|
| FINRA source | `spine/domains/finra/otc_transparency/sources.py` | 1 day |
| FINRA workflow | `spine/domains/finra/otc_transparency/workflows.py` | 1 day |
| FINRA pipeline update | Update existing pipelines | 1 day |
| Quality integration | Add quality checks | 0.5 day |
| Alert integration | Add alerting | 0.5 day |
| End-to-end tests | `tests/integration/` | 1 day |

### Deliverables
- FINRA domain fully integrated with new features
- End-to-end tests passing
- Documentation updated

---

## Phase 6: Frontend Integration (Week 10)

### Dependencies
- Phase 5 complete (domain integration)

### Tasks

| Task | File | Time |
|------|------|------|
| API client | `trading-desktop/src/api/` | 1 day |
| React hooks | `trading-desktop/src/hooks/` | 1 day |
| Pipeline UI | Pipeline status components | 1 day |
| Schedule UI | Schedule management components | 1 day |
| Integration tests | Frontend tests | 0.5 day |
| Documentation | User guide | 0.5 day |

### Deliverables
- Frontend integrated with all new features
- User documentation
- Demo video

---

## Dependency Graph

```
                    ┌─────────────────────────────────────────┐
                    │            Phase 0: Prep                │
                    │         (Environment, Tests)            │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────┴───────────────────────┐
                    │         Phase 1: Core Infrastructure    │
                    │                                         │
                    │  ┌─────────────┐     ┌──────────────┐   │
                    │  │   Errors    │────►│   Storage    │   │
                    │  └─────────────┘     └──────────────┘   │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────┴───────────────────────┐
                    │         Phase 2: Framework Layer        │
                    │                                         │
                    │  ┌─────────────┐     ┌──────────────┐   │
                    │  │   Sources   │     │   Alerts     │   │
                    │  └─────────────┘     └──────────────┘   │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────┴───────────────────────┐
                    │         Phase 3: Orchestration          │
                    │                                         │
                    │  ┌─────────────┐     ┌──────────────┐   │
                    │  │   History   │────►│  Scheduler   │   │
                    │  └─────────────┘     └──────────────┘   │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────┴───────────────────────┐
                    │            Phase 4: API Layer           │
                    │                                         │
                    │  ┌────────────────────────────────────┐ │
                    │  │  Pipeline / History / Scheduler    │ │
                    │  │  Endpoints                         │ │
                    │  └────────────────────────────────────┘ │
                    └─────────────────┬───────────────────────┘
                                      │
         ┌────────────────────────────┴────────────────────────┐
         │                                                     │
┌────────┴─────────┐                               ┌───────────┴──────────┐
│ Phase 5: Domain  │                               │ Phase 6: Frontend    │
│  Integration     │                               │    Integration       │
└──────────────────┘                               └──────────────────────┘
```

---

## File Creation Order

Complete list of files to create, in dependency order:

### Phase 1: Core

```
packages/spine-core/src/spine/core/
├── errors.py                           # Week 2, Day 1-4
└── storage/
    ├── __init__.py                     # Week 3, Day 1
    ├── types.py                        # Week 3, Day 1
    ├── sqlite.py                       # Week 3, Day 2
    ├── postgres.py                     # Week 3, Day 3-4
    ├── db2.py                          # Week 3, Day 4-5
    ├── dialect.py                      # Week 3, Day 5
    └── migrations.py                   # Week 3, Day 5
```

### Phase 2: Framework

```
packages/spine-core/src/spine/framework/
├── sources/
│   ├── __init__.py                     # Week 4, Day 1
│   ├── protocol.py                     # Week 4, Day 1
│   ├── result.py                       # Week 4, Day 1
│   ├── file.py                         # Week 4, Day 2
│   ├── http.py                         # Week 4, Day 3
│   ├── database.py                     # Week 4, Day 4
│   └── registry.py                     # Week 4, Day 5
└── alerts/
    ├── __init__.py                     # Week 5, Day 1
    ├── types.py                        # Week 5, Day 1
    ├── slack.py                        # Week 5, Day 2
    ├── email.py                        # Week 5, Day 3
    ├── servicenow.py                   # Week 5, Day 4
    ├── router.py                       # Week 5, Day 4
    └── throttle.py                     # Week 5, Day 5
```

### Phase 3: Orchestration

```
packages/spine-core/src/spine/orchestration/
├── history/
│   ├── __init__.py                     # Week 6, Day 1
│   ├── types.py                        # Week 6, Day 1
│   ├── store.py                        # Week 6, Day 2-3
│   └── tracker.py                      # Week 6, Day 4
└── scheduler/
    ├── __init__.py                     # Week 7, Day 1
    ├── types.py                        # Week 7, Day 1
    ├── service.py                      # Week 7, Day 2-3
    ├── loader.py                       # Week 7, Day 4
    └── executor.py                     # Week 7, Day 4
```

### Phase 4: API

```
market-spine-intermediate/src/spine/api/
├── pipelines.py                        # Week 8, Day 1
├── history.py                          # Week 8, Day 2
├── scheduler.py                        # Week 8, Day 3
└── finra.py                            # Week 8, Day 4
```

### Phase 5: Domain

```
packages/spine-domains/src/spine/domains/finra/
└── otc_transparency/
    ├── sources.py                      # Week 9, Day 1 (update)
    ├── workflows.py                    # Week 9, Day 2 (new)
    └── pipelines.py                    # Week 9, Day 3 (update)
```

### Phase 6: Frontend

```
trading-desktop/src/
├── api/
│   ├── pipelineApi.ts                  # Week 10, Day 1
│   ├── historyApi.ts                   # Week 10, Day 1
│   ├── schedulerApi.ts                 # Week 10, Day 1
│   └── finraApi.ts                     # Week 10, Day 1
├── hooks/
│   ├── usePipelineStatus.ts            # Week 10, Day 2
│   ├── useSchedules.ts                 # Week 10, Day 2
│   └── useFinraIngest.ts               # Week 10, Day 2
└── components/
    ├── PipelineStatusCard.tsx          # Week 10, Day 3
    ├── ScheduleManager.tsx             # Week 10, Day 4
    └── FINRAIngestPanel.tsx            # Week 10, Day 4
```

---

## Migration Order

Database migrations in order:

```
migrations/
├── basic/
│   └── 0001_source_configs.sql         # Phase 2
├── intermediate/
│   ├── 0001_scheduler_schedules.sql    # Phase 3
│   ├── 0002_scheduler_runs.sql         # Phase 3
│   ├── 0003_workflow_runs.sql          # Phase 3
│   ├── 0004_workflow_step_runs.sql     # Phase 3
│   └── 0005_alert_history.sql          # Phase 3
├── advanced/
│   ├── 0001_dead_letter_queue.sql      # Future
│   └── 0002_circuit_breakers.sql       # Future
├── pg/
│   └── 0001_pg_optimizations.sql       # Phase 3 (if using PostgreSQL)
└── db2/
    └── 0001_db2_schema.sql             # Phase 3 (if using DB2)
```

---

## Testing Strategy

### Unit Tests

- Each module has corresponding test file
- Mock external dependencies (HTTP, SMTP)
- Target 90%+ coverage

### Integration Tests

- Test database adapters against real databases
- Use Docker containers for PostgreSQL
- Separate test databases

### End-to-End Tests

- Full flow from API to database
- Use test FINRA data (mocked)
- Validate frontend integration

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| DB2 driver issues | Early testing with actual DB2 instance |
| APScheduler complexity | Prototype scheduler in isolation first |
| PostgreSQL migration | Parallel testing with SQLite |
| Breaking changes | Feature flags for gradual rollout |
| Performance issues | Load testing before production |

---

## Success Criteria

### Phase 1 Complete
- [ ] All error types implemented
- [ ] SQLite adapter passes tests
- [ ] PostgreSQL adapter passes tests
- [ ] DB2 adapter passes tests

### Phase 2 Complete
- [ ] File source working
- [ ] HTTP source working
- [ ] Database source working
- [ ] Slack alerts working
- [ ] Email alerts working

### Phase 3 Complete
- [ ] Workflow history persisted
- [ ] Scheduler running jobs
- [ ] FINRA scheduled successfully

### Phase 4 Complete
- [ ] All API endpoints documented
- [ ] Postman collection working

### Phase 5 Complete
- [ ] FINRA end-to-end test passing
- [ ] Alerts firing correctly
- [ ] History queryable

### Phase 6 Complete
- [ ] Frontend triggering ingestion
- [ ] Status polling working
- [ ] Schedule management working

---

## Documentation Updates

After each phase, update:

1. **README.md** - New features section
2. **API docs** - OpenAPI spec
3. **User guide** - How to use new features
4. **Architecture docs** - Updated diagrams
5. **LLM prompts** - New patterns and examples

---

## Conclusion

This implementation plan ensures:

1. **Stable foundations** - Core infrastructure first
2. **Incremental delivery** - Working features each phase
3. **Testability** - Tests at each layer
4. **Documentation** - Updated as we go
5. **Low risk** - Dependencies managed

Following this order will result in a complete, tested, and documented platform with all roadmap features implemented.
