# Gap Analysis

> **Purpose:** Document current state vs target state for Basic and Intermediate tiers.
> **Scope:** spine-core, spine-framework, spine-orchestration
> **Last Updated:** 2026-01-11

---

## Current State Summary

### What EXISTS and WORKS

| Component | Location | Status |
|-----------|----------|--------|
| Pipeline registration | `spine.framework.registry` | ✅ Production |
| Pipeline execution | `spine.framework.dispatcher` | ✅ Production |
| Execution context/lineage | `spine.core.execution` | ✅ Production |
| Work manifest (stage tracking) | `spine.core.manifest` | ✅ Production |
| Quality checks | `spine.core.quality` | ✅ Production |
| Rejects/anomalies | `spine.core.rejects` | ✅ Production |
| Source abstraction | `spine.domains.*.sources` | ✅ Per-domain |
| Basic CLI | `market-spine-basic/cli.py` | ✅ Production |
| PipelineGroups (v1 orchestration) | `spine.orchestration` | ✅ Production |
| Workflows (v2 orchestration) | `spine.orchestration` | 🔶 Partial |

### What's MISSING or INCOMPLETE

| Component | Location | Status | Gap |
|-----------|----------|--------|-----|
| Unified source protocol | `spine.framework.sources` | ❌ Missing | No common interface |
| Structured errors | `spine.core.errors` | ❌ Missing | Only SpineError exists |
| Database adapters | `spine.core.storage` | ❌ Missing | Only raw connections |
| Scheduler service | `spine.orchestration.scheduler` | ❌ Missing | No cron support |
| Alerting framework | `spine.framework.alerts` | ❌ Missing | No notification system |
| Workflow history | `spine.orchestration.history` | ❌ Missing | No persistence |

---

## Gap Matrix by Tier

### Basic Tier Gaps

| Gap | Priority | Effort | Module | Description |
|-----|----------|--------|--------|-------------|
| Unified Source Protocol | HIGH | Medium | `spine.framework.sources` | Common interface for all data sources |
| Structured Error Types | HIGH | Low | `spine.core.errors` | Typed errors with categories |
| Result Envelope | HIGH | Low | `spine.core.result` | Consistent success/failure pattern |
| File Source Adapter | MEDIUM | Low | `spine.framework.sources.file` | CSV, PSV, JSON, Parquet |
| Database Source Adapter | MEDIUM | Medium | `spine.framework.sources.database` | Read from tables with pagination |
| Simple Retry | LOW | Low | `spine.framework.retry` | Retry N times with fixed delay |

### Intermediate Tier Gaps

| Gap | Priority | Effort | Module | Description |
|-----|----------|--------|--------|-------------|
| Scheduler Service | HIGH | High | `spine.orchestration.scheduler` | APScheduler-based cron |
| Schedule Registry | HIGH | Medium | `spine.orchestration.schedules` | `@register_schedule` decorator |
| Workflow Run History | HIGH | Medium | `spine.orchestration.history` | Persist runs to database |
| Webhook Alerting | MEDIUM | Medium | `spine.framework.alerts.slack` | POST to Slack on failure |
| Email Alerting | MEDIUM | Medium | `spine.framework.alerts.email` | SMTP for failures |
| API Source Adapter | MEDIUM | Medium | `spine.framework.sources.http` | HTTP client with auth |
| PostgreSQL Adapter | MEDIUM | Medium | `spine.core.storage.postgres` | Production database |
| DB2 Adapter | MEDIUM | Medium | `spine.core.storage.db2` | Enterprise database |

---

## Detailed Gap Analysis

### 1. Unified Source Protocol

**Current State:**
- Each domain has its own source classes
- FINRA: `IngestionSource`, `FileSource`, `APISource`
- Market Data: `PriceSource`, `AlphaVantageSource`
- No common interface

**Problem:**
- Duplicate code across domains
- Inconsistent error handling
- Hard to test sources in isolation
- No composition (e.g., retry wrapper)

**Target State:**
```python
# spine/framework/sources/protocol.py
class Source(Protocol):
    def fetch(self, params: dict) -> SourceResult: ...
    def stream(self, params: dict) -> Iterator[dict]: ...
    
# All domains use the same base
class FinraFileSource(FileSource): ...
class AlphaVantageSource(HttpSource): ...
```

---

### 2. Structured Error Types

**Current State:**
- Single `SpineError` base class
- Orchestration has `GroupError`, `CycleDetectedError`
- No error categories for retry decisions

**Problem:**
- Can't distinguish retryable vs permanent errors
- No error metadata for alerting
- Inconsistent exception handling

**Target State:**
```python
# spine/core/errors.py
class SpineError(Exception):
    category: str = "INTERNAL"
    retryable: bool = False

class SourceError(SpineError):
    category = "SOURCE"

class TransientError(SpineError):
    category = "TRANSIENT"
    retryable = True
```

---

### 3. Database Adapters

**Current State:**
- `spine.framework.db.get_connection()` returns raw SQLite connection
- No abstraction for PostgreSQL or DB2
- SQL syntax tied to SQLite

**Problem:**
- Can't switch databases without code changes
- No connection pooling for production
- DB2 requires different driver and syntax

**Target State:**
```python
# spine/core/storage/protocol.py
class DatabaseAdapter(Protocol):
    def execute(self, sql: str, params: tuple) -> Any: ...
    def executemany(self, sql: str, params_list: list) -> None: ...
    def commit(self) -> None: ...

# Implementations
class SQLiteAdapter(DatabaseAdapter): ...
class PostgreSQLAdapter(DatabaseAdapter): ...
class DB2Adapter(DatabaseAdapter): ...
```

---

### 4. Scheduler Service

**Current State:**
- Manual `spine run` commands
- External cron jobs possible but not managed
- No visibility into scheduled runs

**Problem:**
- No way to see what's scheduled
- No catchup for missed runs
- No dependency between schedules

**Target State:**
```python
# spine/orchestration/scheduler.py
class SchedulerService:
    def start(self): ...
    def stop(self): ...
    def add_schedule(self, schedule: Schedule): ...
    def remove_schedule(self, name: str): ...
    def list_schedules(self) -> list[Schedule]: ...
    def get_next_runs(self, count: int) -> list[ScheduledRun]: ...
```

---

### 5. Alerting Framework

**Current State:**
- No alerting
- Errors only visible in logs
- No integration with incident management

**Problem:**
- Failures go unnoticed
- No escalation path
- Manual monitoring required

**Target State:**
```python
# spine/framework/alerts/protocol.py
class AlertChannel(Protocol):
    def send(self, alert: Alert) -> bool: ...

# Implementations
class SlackChannel(AlertChannel): ...
class EmailChannel(AlertChannel): ...
class ServiceNowChannel(AlertChannel): ...
```

---

### 6. Workflow Run History

**Current State:**
- Workflows execute but don't persist
- No way to query past runs
- No resume from failure

**Problem:**
- Can't audit what ran when
- Can't retry failed workflows
- No visibility for operations

**Target State:**
```python
# spine/orchestration/history.py
class WorkflowHistoryRepository:
    def save_run(self, run: WorkflowRun): ...
    def get_run(self, run_id: str) -> WorkflowRun: ...
    def list_runs(self, workflow: str, limit: int) -> list[WorkflowRun]: ...
    def get_failed_runs(self, since: datetime) -> list[WorkflowRun]: ...
```

---

## Database Schema Gaps

### Current Tables

| Table | Location | Purpose |
|-------|----------|---------|
| `core_manifest` | spine-core | Stage tracking |
| `core_rejects` | spine-core | Validation failures |
| `core_quality` | spine-core | Quality check results |
| `executions` | market-spine-* | Pipeline executions |
| `execution_events` | market-spine-* | Execution lifecycle |

### Missing Tables

| Table | Tier | Purpose |
|-------|------|---------|
| `workflow_runs` | Intermediate | Workflow execution history |
| `workflow_steps` | Intermediate | Step-level details |
| `schedules` | Intermediate | Schedule definitions |
| `schedule_runs` | Intermediate | Scheduled execution history |
| `alerts` | Intermediate | Alert delivery log |
| `alert_channels` | Intermediate | Channel configuration |

---

## File Structure Target

```
packages/spine-core/src/spine/
├── core/
│   ├── __init__.py
│   ├── errors.py           # NEW: Structured error types
│   ├── result.py           # NEW: Result envelope
│   ├── execution.py        # EXISTS
│   ├── manifest.py         # EXISTS
│   ├── quality.py          # EXISTS
│   ├── rejects.py          # EXISTS
│   ├── schema.py           # EXISTS
│   └── storage/            # NEW: Database adapters
│       ├── __init__.py
│       ├── protocol.py     # DatabaseAdapter protocol
│       ├── sqlite.py       # SQLite implementation
│       ├── postgres.py     # PostgreSQL implementation
│       └── db2.py          # DB2 implementation
├── framework/
│   ├── __init__.py
│   ├── dispatcher.py       # EXISTS
│   ├── registry.py         # EXISTS
│   ├── retry.py            # NEW: Simple retry
│   ├── sources/            # NEW: Source protocol + adapters
│   │   ├── __init__.py
│   │   ├── protocol.py     # Source protocol
│   │   ├── file.py         # FileSource (CSV, PSV, JSON)
│   │   ├── http.py         # HttpSource (REST APIs)
│   │   └── database.py     # DatabaseSource (queries)
│   └── alerts/             # NEW: Alerting framework
│       ├── __init__.py
│       ├── protocol.py     # AlertChannel protocol
│       ├── slack.py        # Slack webhook
│       ├── email.py        # SMTP email
│       └── servicenow.py   # ServiceNow incident
└── orchestration/
    ├── __init__.py
    ├── workflow.py         # EXISTS (simplified)
    ├── runner.py           # EXISTS
    ├── scheduler/          # NEW: Scheduler service
    │   ├── __init__.py
    │   ├── service.py      # SchedulerService
    │   ├── registry.py     # @register_schedule
    │   └── cron.py         # Cron expression parsing
    └── history/            # NEW: Run history
        ├── __init__.py
        ├── repository.py   # WorkflowHistoryRepository
        └── models.py       # WorkflowRun, StepRun
```

---

## Next Steps

1. Review [02-SOURCE-PROTOCOL.md](./02-SOURCE-PROTOCOL.md) for source abstraction design
2. Review [03-ERROR-FRAMEWORK.md](./03-ERROR-FRAMEWORK.md) for error handling
3. Review [04-DATABASE-ADAPTERS.md](./04-DATABASE-ADAPTERS.md) for database strategy
4. Review [11-IMPLEMENTATION-ORDER.md](./11-IMPLEMENTATION-ORDER.md) for sequencing
