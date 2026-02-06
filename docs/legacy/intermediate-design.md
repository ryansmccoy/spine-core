# Market Spine Intermediate - Design Document

> **Tier:** 2 of 4  
> **Key Additions:** FastAPI, PostgreSQL, Background Worker, Docker Compose

---

## 1. Overview

Intermediate builds on Basic by adding:
- **FastAPI** REST API (enqueue-only)
- **PostgreSQL** instead of SQLite
- **LocalBackend** with background thread worker
- **Docker Compose** for local development

---

## 2. File Structure

```
market-spine-intermediate/
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
│   ├── 010_otc_trades_raw.sql
│   ├── 011_otc_trades.sql
│   └── 012_otc_metrics_daily.sql
├── src/
│   └── market_spine/
│       ├── __init__.py
│       ├── config.py                 # Pydantic Settings
│       ├── db.py                     # psycopg3 connection pool
│       ├── cli.py                    # Click CLI
│       ├── dispatcher.py             # Submit interface
│       ├── registry.py               # Pipeline registry
│       ├── runner.py                 # run_pipeline(execution_id)
│       ├── api/
│       │   ├── __init__.py
│       │   ├── main.py               # FastAPI app
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   ├── executions.py     # POST/GET executions
│       │   │   ├── health.py         # Health endpoints
│       │   │   └── otc.py            # OTC metrics queries
│       │   └── schemas.py            # Pydantic request/response
│       ├── orchestration/
│       │   ├── __init__.py
│       │   ├── backends/
│       │   │   ├── __init__.py
│       │   │   ├── protocol.py       # OrchestratorBackend Protocol
│       │   │   └── local.py          # LocalBackend (thread-based)
│       │   └── worker.py             # Worker loop
│       ├── pipelines/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── otc.py
│       ├── repositories/
│       │   ├── __init__.py
│       │   ├── executions.py         # Execution CRUD
│       │   └── otc.py                # OTC domain repos
│       └── services/
│           ├── __init__.py
│           ├── otc_connector.py
│           ├── otc_normalizer.py
│           └── otc_metrics.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_api_executions.py
    └── test_api_metrics.py
```

---

## 3. Key Components

### 3.1 Database (PostgreSQL)

```python
# db.py - Connection pool with psycopg3
from psycopg_pool import ConnectionPool

pool: ConnectionPool | None = None

def get_pool() -> ConnectionPool:
    global pool
    if pool is None:
        pool = ConnectionPool(settings.database_url, min_size=2, max_size=10)
    return pool

@contextmanager
def get_connection():
    with get_pool().connection() as conn:
        yield conn
```

### 3.2 Backend Protocol

```python
# orchestration/backends/protocol.py
from typing import Protocol

class OrchestratorBackend(Protocol):
    name: str
    
    async def submit(self, execution_id: str) -> str | None:
        """Submit execution, return backend_run_id if applicable."""
        ...
    
    async def cancel(self, execution_id: str) -> bool:
        """Request cancellation."""
        ...
    
    async def health(self) -> dict:
        """Health check."""
        ...
```

### 3.3 LocalBackend

```python
# orchestration/backends/local.py
class LocalBackend:
    name = "local"
    
    def __init__(self, poll_interval: float = 0.5, max_concurrent: int = 4):
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent
        self._running = False
        self._thread: Thread | None = None
    
    def start(self):
        """Start background worker thread."""
        self._running = True
        self._thread = Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
    
    def _poll_loop(self):
        while self._running:
            # SELECT ... FOR UPDATE SKIP LOCKED
            # Claim and process pending executions
            self._process_pending()
            time.sleep(self.poll_interval)
```

### 3.4 API Routes

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/executions` | Submit pipeline execution |
| GET | `/api/v1/executions` | List executions |
| GET | `/api/v1/executions/{id}` | Get execution by ID |
| GET | `/api/v1/otc/metrics/daily` | Query daily metrics |
| GET | `/api/v1/otc/trades` | Query normalized trades |
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/health/ready` | Readiness probe |

### 3.5 Execution Statuses

```
pending → queued → running → completed
                          ↘ failed
```

(No DLQ in Intermediate - that comes in Advanced)

---

## 4. Docker Compose

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: spine
      POSTGRES_PASSWORD: spine_dev
      POSTGRES_DB: market_spine
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U spine"]
      interval: 5s

  api:
    build: .
    command: ["uvicorn", "market_spine.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://spine:spine_dev@postgres:5432/market_spine
      BACKEND_TYPE: local
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./src:/app/src
      - ./data:/app/data

  worker:
    build: .
    command: ["python", "-m", "market_spine.orchestration.worker"]
    environment:
      DATABASE_URL: postgresql://spine:spine_dev@postgres:5432/market_spine
    depends_on:
      - api

volumes:
  postgres_data:
```

---

## 5. Migrations

### 001_core_executions.sql
```sql
CREATE TABLE executions (
    id TEXT PRIMARY KEY,
    pipeline TEXT NOT NULL,
    params JSONB,
    lane TEXT NOT NULL DEFAULT 'normal',
    trigger_source TEXT NOT NULL,
    logical_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    backend TEXT NOT NULL DEFAULT 'local',
    backend_run_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error TEXT
);

CREATE INDEX idx_executions_status ON executions(status);
CREATE INDEX idx_executions_logical_key ON executions(logical_key) WHERE logical_key IS NOT NULL;
CREATE INDEX idx_executions_pending ON executions(created_at) WHERE status = 'pending';
```

### 002_core_execution_events.sql
```sql
CREATE TABLE execution_events (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL REFERENCES executions(id),
    event_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB,
    idempotency_key TEXT UNIQUE
);

CREATE INDEX idx_events_execution ON execution_events(execution_id, timestamp);
```

---

## 6. API Schemas

```python
# api/schemas.py
class ExecutionCreate(BaseModel):
    pipeline: str
    params: dict[str, Any] = {}
    lane: Literal["normal", "backfill"] = "normal"
    logical_key: str | None = None

class ExecutionResponse(BaseModel):
    id: str
    pipeline: str
    params: dict[str, Any]
    lane: str
    status: str
    trigger_source: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None

class DailyMetricsQuery(BaseModel):
    symbol: str | None = None
    start_date: date | None = None
    end_date: date | None = None

class DailyMetricResponse(BaseModel):
    symbol: str
    date: date
    trade_count: int
    total_volume: float
    total_notional: float
    vwap: float
    high_price: float
    low_price: float
```

---

## 7. Tests

```python
# tests/test_api_executions.py
async def test_submit_execution(client: AsyncClient):
    response = await client.post("/api/v1/executions", json={
        "pipeline": "otc_ingest",
        "params": {}
    })
    assert response.status_code == 202
    data = response.json()
    assert "id" in data
    assert data["status"] == "pending"

# tests/test_api_metrics.py
async def test_query_metrics(client: AsyncClient, seeded_db):
    response = await client.get("/api/v1/otc/metrics/daily", params={
        "symbol": "ACME",
        "start_date": "2026-01-06",
        "end_date": "2026-01-10"
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
```

---

## 8. CLI Commands

```bash
spine db init              # Run migrations
spine db reset             # Reset database
spine run <pipeline>       # Submit via CLI
spine list                 # List pipelines
spine query metrics        # Query metrics
spine worker start         # Start worker (for debugging)
spine shell               # Interactive REPL
```

---

## 9. Key Differences from Basic

| Aspect | Basic | Intermediate |
|--------|-------|--------------|
| Database | SQLite | PostgreSQL |
| Execution | Synchronous | Async (LocalBackend) |
| API | None | FastAPI |
| Backend Protocol | None | Defined |
| Events | None | Basic (created, started, completed, failed) |
| Infrastructure | None | Docker Compose |
