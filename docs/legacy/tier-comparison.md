# Market Spine - Tier Comparison Summary

Quick reference for what changes across tiers.

---

## Feature Matrix

| Feature | Basic | Intermediate | Advanced | Full |
|---------|-------|--------------|----------|------|
| **Database** | SQLite | PostgreSQL | PostgreSQL | PostgreSQL |
| **API** | CLI only | FastAPI | FastAPI | FastAPI |
| **Execution** | Synchronous | LocalBackend (thread) | Local + Celery | Plugin system |
| **Dispatcher** | Simplified | Full interface | + Concurrency | + Backpressure |
| **Events** | None | Basic (4 types) | Full (9 types) | Full + stage |
| **DLQ** | None | None | Full | Full |
| **Concurrency** | None | None | logical_key | logical_key |
| **Retry** | None | None | Policy-based | Policy-based |
| **Health** | Status cmd | /health | Doctor CLI | + Prometheus |
| **Logging** | Console | Console | Structured | JSON + traces |
| **Infrastructure** | None | Docker Compose | + Redis/RabbitMQ | Kubernetes |
| **CI** | None | None | None | GitHub Actions |
| **Cleanup** | None | None | None | CronJob |

---

## Orchestration Features by Tier

| Feature | Basic | Intermediate | Advanced | Full |
|---------|-------|--------------|----------|------|
| **PipelineGroups (v1)** | ✓ | ✓ | ✓ | ✓ |
| **Workflows (v2)** | ✓ | ✓ | ✓ | ✓ |
| **Lambda Steps** | ✓ | ✓ | ✓ | ✓ |
| **Pipeline Steps** | ✓ | ✓ | ✓ | ✓ |
| **Context Passing** | ✓ | ✓ | ✓ | ✓ |
| **Quality Gates** | ✓ | ✓ | ✓ | ✓ |
| **Choice Steps** | - | ✓ | ✓ | ✓ |
| **Run History** | - | ✓ | ✓ | ✓ |
| **Map Steps** | - | - | ✓ | ✓ |
| **Wait Steps** | - | - | ✓ | ✓ |
| **Checkpointing** | - | - | ✓ | ✓ |
| **Resume** | - | - | ✓ | ✓ |
| **Sub-workflows** | - | - | - | ✓ |
| **Workflow Versioning** | - | - | - | ✓ |

### Orchestration Tier Details

**Basic Tier:**
- `Workflow` and `Step` types for defining execution flow
- `Step.lambda_()` - inline Python function steps
- `Step.pipeline()` - invoke registered pipelines
- `WorkflowContext` - immutable context passed step-to-step
- `StepResult` - result envelope with quality metrics
- Sequential execution only

**Intermediate Tier:**
- `Step.choice()` - conditional branching based on context values
- Persistent run history (workflow_runs table)
- Run status tracking and querying

**Advanced Tier:**
- `Step.map()` - fan-out to parallel executions, fan-in results
- `Step.wait()` - delay or scheduled continuation
- Checkpointing - save/resume workflow state
- Resume from last checkpoint after failure

**Full Tier:**
- Sub-workflow invocation (workflow calls workflow)
- Workflow versioning for safe migrations
- Distributed execution coordination

---

## Status State Machine Evolution

### Basic
```
pending → running → completed | failed
```

### Intermediate
```
pending → queued → running → completed | failed
```

### Advanced / Full
```
pending → queued → running → completed
    ↓         ↓        ↓
    └─────────┴────────┴──→ failed → dead_lettered
                       ↓
                  cancelling → cancelled
```

---

## Event Types by Tier

| Event | Basic | Intermediate | Advanced | Full |
|-------|-------|--------------|----------|------|
| `created` | - | ✓ | ✓ | ✓ |
| `queued` | - | ✓ | ✓ | ✓ |
| `started` | - | ✓ | ✓ | ✓ |
| `completed` | - | ✓ | ✓ | ✓ |
| `failed` | - | - | ✓ | ✓ |
| `dead_lettered` | - | - | ✓ | ✓ |
| `cancelled` | - | - | ✓ | ✓ |
| `stage_started` | - | - | - | ✓ |
| `stage_completed` | - | - | - | ✓ |
| `stage_failed` | - | - | - | ✓ |

---

## API Endpoints by Tier

| Endpoint | Basic | Intermediate | Advanced | Full |
|----------|-------|--------------|----------|------|
| `POST /executions` | - | ✓ | ✓ | ✓ |
| `GET /executions` | - | ✓ | ✓ | ✓ |
| `GET /executions/{id}` | - | ✓ | ✓ | ✓ |
| `GET /executions/{id}/events` | - | - | ✓ | ✓ |
| `POST /executions/{id}/cancel` | - | - | ✓ | ✓ |
| `GET /dead-letters` | - | - | ✓ | ✓ |
| `POST /dead-letters/{id}/retry` | - | - | ✓ | ✓ |
| `GET /otc/metrics/daily` | - | ✓ | ✓ | ✓ |
| `GET /otc/trades` | - | ✓ | ✓ | ✓ |
| `GET /health` | - | ✓ | ✓ | ✓ |
| `GET /health/ready` | - | ✓ | ✓ | ✓ |
| `GET /health/metrics` | - | - | ✓ | ✓ |

---

## Backends by Tier

| Backend | Basic | Intermediate | Advanced | Full |
|---------|-------|--------------|----------|------|
| Sync (inline) | ✓ | - | - | - |
| LocalBackend | - | ✓ | ✓ | ✓ |
| CeleryBackend | - | - | ✓ | ✓ |
| PrefectBackend | - | - | - | Stub |
| DagsterBackend | - | - | - | Stub |
| TemporalBackend | - | - | - | Stub |

---

## CLI Commands by Tier

| Command | Basic | Intermediate | Advanced | Full |
|---------|-------|--------------|----------|------|
| `spine db init` | ✓ | ✓ | ✓ | ✓ |
| `spine run <pipeline>` | ✓ | ✓ | ✓ | ✓ |
| `spine list` | ✓ | ✓ | ✓ | ✓ |
| `spine query metrics` | ✓ | ✓ | ✓ | ✓ |
| `spine shell` | ✓ | ✓ | ✓ | ✓ |
| `spine worker start` | - | ✓ | ✓ | ✓ |
| `spine doctor` | - | - | ✓ | ✓ |
| `spine dlq list` | - | - | ✓ | ✓ |
| `spine dlq retry` | - | - | ✓ | ✓ |
| `spine cleanup run` | - | - | - | ✓ |

---

## Database Tables by Tier

| Table | Basic | Intermediate | Advanced | Full |
|-------|-------|--------------|----------|------|
| `_migrations` | ✓ | ✓ | ✓ | ✓ |
| `executions` | ✓ (simple) | ✓ (full) | ✓ (+ parent) | ✓ |
| `execution_events` | - | ✓ | ✓ | ✓ |
| `dead_letters` | - | - | ✓ | ✓ |
| `otc_trades_raw` | ✓ | ✓ | ✓ | ✓ |
| `otc_trades` | ✓ | ✓ | ✓ | ✓ |
| `otc_metrics_daily` | ✓ | ✓ | ✓ | ✓ |

---

## Test Coverage by Tier

| Test Type | Basic | Intermediate | Advanced | Full |
|-----------|-------|--------------|----------|------|
| Normalizer unit | ✓ | ✓ | ✓ | ✓ |
| Metrics unit | ✓ | ✓ | ✓ | ✓ |
| API tests | - | ✓ | ✓ | ✓ |
| Dispatcher invariants | - | - | ✓ | ✓ |
| Concurrency tests | - | - | ✓ | ✓ |
| DLQ tests | - | - | ✓ | ✓ |
| Architecture tests | - | - | - | ✓ |
| Integration (e2e) | - | - | - | ✓ |

---

## Infrastructure by Tier

| Component | Basic | Intermediate | Advanced | Full |
|-----------|-------|--------------|----------|------|
| Docker Compose | - | ✓ | ✓ | ✓ |
| PostgreSQL | - | ✓ | ✓ | ✓ |
| Redis | - | - | ✓ | ✓ |
| RabbitMQ | - | - | Optional | Optional |
| Kubernetes | - | - | - | ✓ |
| Helm Chart | - | - | - | ✓ |
| HPA | - | - | - | ✓ |
| ServiceMonitor | - | - | - | ✓ |
| CronJob (cleanup) | - | - | - | ✓ |

---

## Upgrade Path

### Basic → Intermediate
- Replace SQLite with PostgreSQL
- Add FastAPI layer
- Implement LocalBackend
- Add execution_events table
- Wrap CLI commands with API calls
- **Orchestration:** Add workflow_runs table, enable Choice steps

### Intermediate → Advanced
- Add dead_letters table
- Implement concurrency guard (unique index)
- Add CeleryBackend option
- Implement retry policy
- Add doctor CLI
- Add stage events
- **Orchestration:** Enable Map/Wait steps, add checkpointing

### Advanced → Full
- Add Helm chart + K8s manifests
- Implement backend plugin loader
- Add Prometheus metrics
- Add CI guardrails
- Add cleanup CronJob
- Add backpressure guard
- Add architecture tests
- **Orchestration:** Enable sub-workflows, add workflow versioning
