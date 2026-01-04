# Market Spine Advanced - Design Document

> **Tier:** 3 of 4  
> **Key Additions:** Celery Backend, Redis, DLQ, Concurrency Guards, Full Event Sourcing

---

## 1. Overview

Advanced implements the full event-sourced orchestration:
- **CeleryBackend** as optional backend (LocalBackend still default)
- **Dead Letter Queue** with retry semantics
- **Concurrency guards** via `logical_key`
- **Full execution events** including stage events
- **Doctor CLI** for health diagnostics

---

## 2. File Structure

```
market-spine-advanced/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── README.md
├── data/
│   └── otc_sample.csv
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
│       ├── dispatcher.py             # Full dispatcher with concurrency
│       ├── registry.py
│       ├── runner.py                 # run_pipeline(execution_id)
│       ├── api/
│       │   ├── __init__.py
│       │   ├── main.py
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   ├── executions.py
│       │   │   ├── dead_letters.py   # DLQ endpoints
│       │   │   ├── health.py         # Ledger-based health
│       │   │   └── otc.py
│       │   └── schemas.py
│       ├── orchestration/
│       │   ├── __init__.py
│       │   ├── concurrency.py        # Logical key guards
│       │   ├── dlq.py                # DLQ management
│       │   ├── events.py             # Event emission
│       │   ├── retry.py              # Retry policy
│       │   ├── backends/
│       │   │   ├── __init__.py
│       │   │   ├── protocol.py
│       │   │   ├── local.py
│       │   │   └── celery.py         # CeleryBackend
│       │   └── worker.py
│       ├── pipelines/
│       │   ├── __init__.py
│       │   ├── base.py               # Stage model
│       │   └── otc.py                # Including backfill_range
│       ├── repositories/
│       │   ├── __init__.py
│       │   ├── executions.py
│       │   ├── events.py
│       │   ├── dead_letters.py
│       │   └── otc.py
│       └── services/
│           ├── __init__.py
│           ├── otc_connector.py
│           ├── otc_normalizer.py
│           └── otc_metrics.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_dispatcher_invariants.py
    ├── test_concurrency.py
    └── test_dlq.py
```

---

## 3. Execution Ledger Schema

### executions (enhanced)
```sql
CREATE TABLE executions (
    id TEXT PRIMARY KEY,
    pipeline TEXT NOT NULL,
    params JSONB,
    lane TEXT NOT NULL DEFAULT 'normal',
    trigger_source TEXT NOT NULL,
    logical_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    backend TEXT NOT NULL,
    backend_run_id TEXT,
    parent_execution_id TEXT REFERENCES executions(id),
    retry_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error TEXT,
    result JSONB
);

-- Concurrency guard index
CREATE UNIQUE INDEX idx_executions_logical_key_active 
ON executions(logical_key) 
WHERE logical_key IS NOT NULL 
  AND status IN ('pending', 'queued', 'running');
```

### execution_events
```sql
CREATE TABLE execution_events (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL REFERENCES executions(id),
    event_type TEXT NOT NULL,
    stage TEXT,                        -- For stage-level events
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB,
    idempotency_key TEXT UNIQUE
);
```

### dead_letters
```sql
CREATE TABLE dead_letters (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL UNIQUE REFERENCES executions(id),
    reason TEXT NOT NULL,
    retry_count INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    resolution TEXT  -- 'retried', 'discarded', 'fixed'
);
```

---

## 4. Status State Machine

```
pending → queued → running → completed
    ↓         ↓        ↓
    └─────────┴────────┴──→ failed → dead_lettered
                       ↓
                  cancelling → cancelled
```

**Event Types:**
- `created`, `queued`, `started`, `completed`, `failed`
- `dead_lettered`, `cancelled`
- `stage_started`, `stage_completed`, `stage_failed`

---

## 5. Concurrency Guard

```python
# orchestration/concurrency.py
class ConcurrencyGuard:
    def acquire(self, logical_key: str, execution_id: str) -> bool:
        """
        Attempt to acquire lock for logical_key.
        Uses unique partial index on executions table.
        """
        # INSERT will fail if active execution with same logical_key exists
        try:
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO executions (id, ..., logical_key, status)
                    VALUES (%s, ..., %s, 'pending')
                """, (execution_id, ..., logical_key))
                return True
        except UniqueViolation:
            return False
    
    def release(self, logical_key: str):
        """Released automatically when status leaves active states."""
        pass
```

---

## 6. Dead Letter Queue

```python
# orchestration/dlq.py
class DeadLetterQueue:
    def add(self, execution_id: str, reason: str, retry_count: int):
        """Move execution to DLQ."""
        with transaction() as conn:
            conn.execute("""
                UPDATE executions SET status = 'dead_lettered' WHERE id = %s
            """, (execution_id,))
            conn.execute("""
                INSERT INTO dead_letters (id, execution_id, reason, retry_count)
                VALUES (%s, %s, %s, %s)
            """, (ulid(), execution_id, reason, retry_count))
            self._emit_event(execution_id, 'dead_lettered', {'reason': reason})
    
    def retry(self, dead_letter_id: str, user: str) -> str:
        """
        Retry from DLQ. Creates NEW execution.
        Returns new execution_id.
        """
        dl = self.get(dead_letter_id)
        original = execution_repo.get(dl.execution_id)
        
        new_execution_id = dispatcher.submit(
            pipeline=original.pipeline,
            params=original.params,
            lane=original.lane,
            trigger_source='retry',
            logical_key=original.logical_key,
            parent_execution_id=original.id
        )
        
        self._resolve(dead_letter_id, user, 'retried')
        return new_execution_id
```

---

## 7. Retry Policy

```python
# orchestration/retry.py
@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff: Literal["fixed", "exponential"] = "exponential"
    base_delay_seconds: float = 30.0
    max_delay_seconds: float = 3600.0

    def should_retry(self, retry_count: int) -> bool:
        return retry_count < self.max_retries

    def get_delay(self, retry_count: int) -> float:
        if self.backoff == "fixed":
            return self.base_delay_seconds
        delay = self.base_delay_seconds * (2 ** retry_count)
        return min(delay, self.max_delay_seconds)
```

---

## 8. CeleryBackend

```python
# orchestration/backends/celery.py
from celery import Celery

class CeleryBackend:
    name = "celery"
    
    def __init__(self, broker_url: str, result_backend: str):
        self.app = Celery('market_spine', broker=broker_url, backend=result_backend)
        self._register_task()
    
    def _register_task(self):
        @self.app.task(name='run_pipeline', bind=True)
        def run_pipeline_task(self, execution_id: str):
            from market_spine.runner import run_pipeline
            return run_pipeline(execution_id)
    
    async def submit(self, execution_id: str) -> str:
        # Map lane to queue
        execution = await execution_repo.get(execution_id)
        queue = f"pipelines.{execution.lane}"
        
        result = self.app.send_task(
            'run_pipeline',
            args=[execution_id],
            queue=queue
        )
        return result.id  # backend_run_id
    
    async def cancel(self, execution_id: str) -> bool:
        execution = await execution_repo.get(execution_id)
        if execution.backend_run_id:
            self.app.control.revoke(execution.backend_run_id, terminate=True)
            return True
        return False
```

---

## 9. API Endpoints (Additional)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/executions/{id}/events` | Execution event history |
| GET | `/api/v1/dead-letters` | List DLQ entries |
| GET | `/api/v1/dead-letters/{id}` | Get DLQ entry |
| POST | `/api/v1/dead-letters/{id}/retry` | Retry from DLQ |
| POST | `/api/v1/dead-letters/{id}/discard` | Discard DLQ entry |
| GET | `/api/v1/health/metrics` | Ledger-derived metrics |

---

## 10. Doctor CLI

```python
# cli.py - doctor command
@cli.command()
def doctor():
    """Run health diagnostics."""
    checks = [
        ("Database", check_db_connection),
        ("Redis", check_redis_connection),
        ("Backend", check_backend_health),
        ("Pending Executions", check_pending_count),
        ("DLQ", check_dlq_size),
        ("Stuck Running", check_stuck_running),
        ("Orphan Pending", check_orphan_pending),
    ]
    
    for name, check_fn in checks:
        try:
            result = check_fn()
            if result.ok:
                console.print(f"✓ {name}: {result.message}")
            else:
                console.print(f"✗ {name}: {result.message}", style="red")
        except Exception as e:
            console.print(f"✗ {name}: Error - {e}", style="red")
```

**Health Metrics (ledger-derived):**
```sql
-- Pending executions
SELECT COUNT(*) FROM executions WHERE status = 'pending';

-- Failed last hour
SELECT COUNT(*) FROM executions 
WHERE status = 'failed' AND completed_at > NOW() - INTERVAL '1 hour';

-- DLQ unresolved
SELECT COUNT(*) FROM dead_letters WHERE resolved_at IS NULL;

-- Stuck running (> 1 hour)
SELECT COUNT(*) FROM executions 
WHERE status = 'running' AND started_at < NOW() - INTERVAL '1 hour';

-- Orphan pending (no backend_run_id after 5 min)
SELECT COUNT(*) FROM executions 
WHERE status = 'pending' 
  AND created_at < NOW() - INTERVAL '5 minutes'
  AND backend_run_id IS NULL;
```

---

## 11. Backfill Pipeline

```python
# pipelines/otc.py
@register_pipeline("otc_backfill_range")
class OTCBackfillRangePipeline(Pipeline):
    name = "otc_backfill_range"
    description = "Backfill OTC data for date range"
    
    stages = [
        Stage(name="ingest", fn=run_ingest),
        Stage(name="normalize", fn=run_normalize),
        Stage(name="compute", fn=run_compute),
    ]
    
    params_schema = BackfillParams  # start_date, end_date, symbols
    default_lane = "backfill"
    
    def get_logical_key(self, params: dict) -> str:
        # Per-symbol-per-day concurrency
        return f"otc_backfill:{params['symbol']}:{params['date']}"
```

---

## 12. Docker Compose

```yaml
services:
  postgres:
    image: postgres:16-alpine
    # ... same as intermediate

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]

  rabbitmq:
    image: rabbitmq:3-management-alpine
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: spine
      RABBITMQ_DEFAULT_PASS: spine_dev

  api:
    build: .
    command: ["uvicorn", "market_spine.api.main:app", "--host", "0.0.0.0"]
    environment:
      DATABASE_URL: postgresql://spine:spine_dev@postgres:5432/market_spine
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: amqp://spine:spine_dev@rabbitmq:5672//
      BACKEND_TYPE: ${BACKEND_TYPE:-local}
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }

  worker:
    build: .
    command: ["python", "-m", "market_spine.orchestration.worker"]
    environment:
      # Same as api
    depends_on:
      - api
    deploy:
      replicas: 2

  # Optional: Celery worker (when BACKEND_TYPE=celery)
  celery-worker:
    build: .
    command: ["celery", "-A", "market_spine.celery_app", "worker", "-Q", "pipelines.normal,pipelines.backfill"]
    profiles: ["celery"]
    # ...
```

---

## 13. Tests

```python
# test_dispatcher_invariants.py
async def test_api_is_enqueue_only(client):
    """API returns immediately, does not execute pipeline."""
    start = time.time()
    response = await client.post("/api/v1/executions", json={
        "pipeline": "otc_ingest"
    })
    elapsed = time.time() - start
    
    assert response.status_code == 202
    assert elapsed < 0.5  # Should return immediately
    assert response.json()["status"] == "pending"

async def test_duplicate_logical_key_rejected(dispatcher):
    """Concurrent execution with same logical_key is rejected."""
    exec1 = await dispatcher.submit("otc_ingest", logical_key="ACME:2026-01-06")
    
    with pytest.raises(ConcurrencyConflict):
        await dispatcher.submit("otc_ingest", logical_key="ACME:2026-01-06")

async def test_retry_creates_new_execution(dlq, dispatcher):
    """DLQ retry creates new execution linked to parent."""
    # Create and fail execution
    exec1 = await create_failed_execution()
    dl = await dlq.add(exec1.id, "test failure", retry_count=3)
    
    # Retry
    new_exec_id = await dlq.retry(dl.id, user="test")
    new_exec = await execution_repo.get(new_exec_id)
    
    assert new_exec.id != exec1.id
    assert new_exec.parent_execution_id == exec1.id
    assert new_exec.trigger_source == "retry"
```

---

## 14. Key Differences from Intermediate

| Aspect | Intermediate | Advanced |
|--------|--------------|----------|
| Backend | LocalBackend only | Local + Celery |
| DLQ | None | Full implementation |
| Concurrency | None | logical_key guards |
| Events | Basic | Full (incl. stage events) |
| Retry | None | Policy-based |
| Health | Simple | Ledger-derived metrics |
| Infrastructure | Postgres only | + Redis + RabbitMQ |
