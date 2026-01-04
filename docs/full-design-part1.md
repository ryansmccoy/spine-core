# Market Spine Full - Design Document (Part 1: Core)

> **Tier:** 4 of 4  
> **Key Additions:** Kubernetes, Helm, Backend Plugins, Observability, CI Guardrails

---

## 1. Overview

Full is production-grade with:
- **Kubernetes manifests + Helm chart**
- **Backend plugin system** (Celery + stubs for Prefect/Dagster/Temporal)
- **Prometheus metrics + structured logging**
- **CI guardrails** enforcing architectural invariants
- **Retention/cleanup jobs**
- **Backpressure safeguards**

---

## 2. File Structure

```
market-spine-full/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── docker-build.yml
│       └── helm-lint.yml
├── docker/
│   ├── Dockerfile
│   ├── Dockerfile.migrations
│   └── docker-compose.yml
├── helm/
│   └── market-spine/
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── values-production.yaml
│       ├── templates/
│       │   ├── _helpers.tpl
│       │   ├── configmap.yaml
│       │   ├── secret.yaml
│       │   ├── api-deployment.yaml
│       │   ├── api-service.yaml
│       │   ├── worker-deployment.yaml
│       │   ├── beat-deployment.yaml
│       │   ├── migration-job.yaml
│       │   ├── cleanup-cronjob.yaml
│       │   ├── ingress.yaml
│       │   ├── hpa.yaml
│       │   ├── pdb.yaml
│       │   └── servicemonitor.yaml
│       └── tests/
│           └── test-connection.yaml
├── k8s/
│   └── manifests/               # Plain manifests (generated from Helm)
│       ├── namespace.yaml
│       ├── api.yaml
│       ├── worker.yaml
│       └── ...
├── migrations/
│   ├── 001_core_executions.sql
│   ├── 002_core_execution_events.sql
│   ├── 003_core_dead_letters.sql
│   ├── 010_otc_trades_raw.sql
│   ├── 011_otc_trades.sql
│   └── 012_otc_metrics_daily.sql
├── src/
│   └── market_spine/
│       ├── __init__.py
│       ├── config.py
│       ├── db.py
│       ├── cli.py
│       ├── dispatcher.py
│       ├── registry.py
│       ├── runner.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── main.py
│       │   ├── middleware.py         # Request ID, logging
│       │   ├── routes/
│       │   │   ├── executions.py
│       │   │   ├── dead_letters.py
│       │   │   ├── health.py
│       │   │   └── otc.py
│       │   └── schemas.py
│       ├── orchestration/
│       │   ├── __init__.py
│       │   ├── concurrency.py
│       │   ├── dlq.py
│       │   ├── events.py
│       │   ├── retry.py
│       │   ├── backpressure.py       # Queue depth limits
│       │   ├── backends/
│       │   │   ├── __init__.py
│       │   │   ├── protocol.py
│       │   │   ├── loader.py         # Entrypoint-based loading
│       │   │   ├── local.py
│       │   │   ├── celery.py
│       │   │   ├── prefect.py        # Stub
│       │   │   ├── dagster.py        # Stub
│       │   │   └── temporal.py       # Stub
│       │   └── worker.py
│       ├── observability/
│       │   ├── __init__.py
│       │   ├── metrics.py            # Prometheus metrics
│       │   ├── logging.py            # Structured JSON logs
│       │   └── tracing.py            # OpenTelemetry hooks (optional)
│       ├── jobs/
│       │   ├── __init__.py
│       │   ├── cleanup.py            # Retention cleanup
│       │   └── reconciliation.py     # Orphan detection
│       ├── pipelines/
│       │   └── ...
│       ├── repositories/
│       │   └── ...
│       └── services/
│           └── ...
├── tests/
│   ├── unit/
│   ├── integration/
│   │   └── test_e2e.py              # Docker-compose based
│   └── architecture/
│       ├── test_no_forbidden_imports.py
│       └── test_invariants.py
├── scripts/
│   ├── run-e2e-tests.sh
│   └── generate-manifests.sh
├── data/
│   └── otc_sample.csv
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

---

## 3. Backend Plugin System

### 3.1 Protocol (unchanged from Advanced)

```python
# orchestration/backends/protocol.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class OrchestratorBackend(Protocol):
    name: str
    
    async def submit(self, execution_id: str) -> str | None: ...
    async def cancel(self, execution_id: str) -> bool: ...
    async def status(self, execution_id: str) -> dict: ...
    async def health(self) -> dict: ...
    async def queue_depths(self) -> dict[str, int]: ...
```

### 3.2 Entrypoint Loading

```python
# orchestration/backends/loader.py
from importlib.metadata import entry_points

def load_backend(name: str) -> OrchestratorBackend:
    """Load backend by name via entrypoints or builtin."""
    builtins = {
        "local": "market_spine.orchestration.backends.local:LocalBackend",
        "celery": "market_spine.orchestration.backends.celery:CeleryBackend",
    }
    
    if name in builtins:
        module_path, class_name = builtins[name].rsplit(":", 1)
        module = import_module(module_path)
        return getattr(module, class_name)()
    
    # Check entrypoints
    eps = entry_points(group="market_spine.backends")
    for ep in eps:
        if ep.name == name:
            return ep.load()()
    
    raise ValueError(f"Unknown backend: {name}")
```

### 3.3 pyproject.toml Entry Points

```toml
[project.entry-points."market_spine.backends"]
local = "market_spine.orchestration.backends.local:LocalBackend"
celery = "market_spine.orchestration.backends.celery:CeleryBackend"
# Third-party backends register their own entrypoints
```

---

## 4. Backend Stubs

### Prefect Stub
```python
# orchestration/backends/prefect.py
class PrefectBackend:
    """
    Stub for Prefect backend.
    
    Implementation notes:
    - Use prefect.deployments.run_deployment() for submit
    - Map lanes to work pools
    - Store flow_run_id as backend_run_id
    """
    name = "prefect"
    
    async def submit(self, execution_id: str) -> str:
        raise NotImplementedError(
            "Prefect backend not implemented. See docs/backends/prefect.md"
        )
    # ...
```

### Dagster Stub
```python
# orchestration/backends/dagster.py
class DagsterBackend:
    """
    Stub for Dagster backend.
    
    Implementation notes:
    - Use dagster_graphql client for submit_job
    - Map pipelines to Dagster jobs
    - Store run_id as backend_run_id
    """
    name = "dagster"
    # ...
```

### Temporal Stub
```python
# orchestration/backends/temporal.py
class TemporalBackend:
    """
    Stub for Temporal backend.
    
    Implementation notes:
    - Use temporalio.client.Client for start_workflow
    - Map lanes to task queues
    - Store workflow_id as backend_run_id
    """
    name = "temporal"
    # ...
```

---

## 5. Observability

### 5.1 Prometheus Metrics

```python
# observability/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Counters
executions_submitted = Counter(
    'spine_executions_submitted_total',
    'Total executions submitted',
    ['pipeline', 'lane', 'trigger_source']
)

executions_completed = Counter(
    'spine_executions_completed_total',
    'Total executions completed',
    ['pipeline', 'status']
)

# Histograms
execution_duration = Histogram(
    'spine_execution_duration_seconds',
    'Execution duration',
    ['pipeline'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)

# Gauges (from ledger queries)
pending_executions = Gauge(
    'spine_pending_executions',
    'Current pending executions',
    ['lane']
)

dlq_size = Gauge(
    'spine_dlq_unresolved',
    'Unresolved dead letters'
)
```

### 5.2 Metrics Endpoint

```python
# api/routes/health.py
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

@router.get("/metrics")
async def metrics():
    # Refresh gauge values from ledger
    await refresh_ledger_metrics()
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
```

### 5.3 Structured Logging

```python
# observability/logging.py
import structlog

def configure_logging(json_format: bool = True):
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    
    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(processors=processors)

# Usage in code
logger = structlog.get_logger()
logger.info("execution_started", execution_id=exec_id, pipeline=pipeline)
```

---

## 6. Backpressure

```python
# orchestration/backpressure.py
class BackpressureGuard:
    def __init__(self, max_pending: int = 1000, max_per_lane: dict[str, int] | None = None):
        self.max_pending = max_pending
        self.max_per_lane = max_per_lane or {"normal": 500, "backfill": 200}
    
    async def check(self, lane: str) -> None:
        """Raise if backpressure limits exceeded."""
        pending = await self._get_pending_count(lane)
        
        if pending >= self.max_per_lane.get(lane, self.max_pending):
            raise BackpressureExceeded(
                f"Lane '{lane}' has {pending} pending executions (limit: {self.max_per_lane[lane]})"
            )
        
        total_pending = await self._get_total_pending()
        if total_pending >= self.max_pending:
            raise BackpressureExceeded(
                f"Total pending executions: {total_pending} (limit: {self.max_pending})"
            )
```

---

## 7. Cleanup Jobs

```python
# jobs/cleanup.py
class RetentionCleanup:
    def __init__(
        self,
        execution_retention_days: int = 30,
        event_retention_days: int = 30,
        raw_data_retention_days: int = 180,
    ):
        self.execution_retention_days = execution_retention_days
        self.event_retention_days = event_retention_days
        self.raw_data_retention_days = raw_data_retention_days
    
    async def run(self) -> dict:
        """Run cleanup job. Returns counts of deleted records."""
        stats = {}
        
        # Clean old execution events
        stats["events_deleted"] = await self._clean_events()
        
        # Clean resolved dead letters
        stats["dead_letters_deleted"] = await self._clean_dead_letters()
        
        # Clean old raw trade data
        stats["raw_trades_deleted"] = await self._clean_raw_trades()
        
        return stats
    
    async def _clean_events(self) -> int:
        cutoff = datetime.now() - timedelta(days=self.event_retention_days)
        result = await db.execute("""
            DELETE FROM execution_events
            WHERE timestamp < %s
            AND execution_id IN (
                SELECT id FROM executions 
                WHERE status IN ('completed', 'failed', 'dead_lettered', 'cancelled')
            )
        """, (cutoff,))
        return result.rowcount
```
