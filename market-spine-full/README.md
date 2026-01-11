# Market Spine Full

Production-grade Market Spine analytics pipeline with Kubernetes support, observability, and enterprise features.

## Features

- **Kubernetes-Ready**: Deployments, services, ConfigMaps, and init containers
- **Event-Sourced Orchestration**: Full execution ledger with replay capability
- **TimescaleDB**: Hypertable partitioning and automatic compression for time-series data
- **Observability**: Prometheus metrics, structured logging, OpenTelemetry tracing
- **Dead Letter Queue**: Failed execution tracking with retry capability
- **Celery Backend**: Distributed task processing with Redis broker
- **CI/CD**: GitHub Actions with tests, linting, and invariant checks
- **Retention Policies**: Automatic cleanup of old executions and data

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│    API      │    │   Worker    │    │    Beat     │
│  (FastAPI)  │    │  (Celery)   │    │ (Scheduler) │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                   │
       └────────┬─────────┴───────────────────┘
                │
       ┌────────▼────────┐
       │      Redis      │
       │    (Broker)     │
       └────────┬────────┘
                │
       ┌────────▼────────┐
       │   TimescaleDB   │
       │   (Postgres)    │
       └─────────────────┘
```

## Quick Start

### Docker Compose (Development)

```bash
# Start all services
docker compose up -d

# Run migrations
docker compose exec api spine db migrate

# View logs
docker compose logs -f api worker beat

# Check health
curl http://localhost:8000/health
```

### Kubernetes (Production)

```bash
# Create namespace
kubectl create namespace market-spine

# Apply ConfigMap and Secrets
kubectl apply -f k8s/configmap.yaml -n market-spine
kubectl apply -f k8s/secrets.yaml -n market-spine

# Run database migrations
kubectl apply -f k8s/migration-job.yaml -n market-spine
kubectl wait --for=condition=complete job/spine-migration -n market-spine

# Deploy services
kubectl apply -f k8s/api-deployment.yaml -n market-spine
kubectl apply -f k8s/worker-deployment.yaml -n market-spine
kubectl apply -f k8s/beat-deployment.yaml -n market-spine

# Expose API
kubectl apply -f k8s/api-service.yaml -n market-spine
```

## Running Locally

```bash
# Install dependencies
uv sync --all-extras

# Set environment variables
export DATABASE_URL="postgresql://spine:spine@localhost:5432/spine"
export REDIS_URL="redis://localhost:6379/0"

# Run migrations
uv run spine db migrate

# Start services (in separate terminals)
uv run uvicorn market_spine.api.main:app --reload --port 8000
uv run celery -A market_spine.celery_app worker -l info
uv run celery -A market_spine.celery_app beat -l info

# Or use the CLI
uv run spine worker start
uv run spine beat start
```

## Running Pipelines

### Via API

```bash
# Submit OTC ingest pipeline
curl -X POST http://localhost:8000/executions \
  -H "Content-Type: application/json" \
  -d '{"pipeline": "otc_ingest", "params": {}}'

# Submit full ETL (ingest + normalize + compute)
curl -X POST http://localhost:8000/executions \
  -H "Content-Type: application/json" \
  -d '{"pipeline": "otc_full_etl", "params": {}}'

# Submit backfill for date range
curl -X POST http://localhost:8000/executions \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline": "otc_backfill_range",
    "params": {"start_date": "2024-01-01", "end_date": "2024-01-31"}
  }'

# Check execution status
curl http://localhost:8000/executions/{execution_id}

# View execution events
curl http://localhost:8000/executions/{execution_id}/events
```

### Via CLI

```bash
# Run pipeline directly (bypasses queue)
uv run spine pipeline run otc_ingest

# Submit to queue
uv run spine dispatch otc_ingest

# Submit backfill
uv run spine dispatch otc_backfill_range --param start_date=2024-01-01 --param end_date=2024-01-31

# Check status
uv run spine execution status <execution_id>

# Run doctor diagnostics
uv run spine doctor
```

## Querying Results

### Via API

```bash
# Get daily metrics for a symbol
curl "http://localhost:8000/otc/metrics/daily?symbol=AAPL&start=2024-01-01&end=2024-01-31"

# Get trades
curl "http://localhost:8000/otc/trades?symbol=AAPL&start=2024-01-01&end=2024-01-31"
```

### Via CLI

```bash
uv run spine query metrics AAPL --start 2024-01-01 --end 2024-01-31
```

## Dead Letter Queue

```bash
# View dead letters
curl http://localhost:8000/dead-letters

# Retry a failed execution (creates NEW execution)
curl -X POST http://localhost:8000/dead-letters/{id}/retry
```

## Observability

### Metrics (Prometheus)

```bash
# Prometheus metrics endpoint
curl http://localhost:8000/metrics

# Key metrics:
# - spine_executions_total{pipeline,status}
# - spine_execution_duration_seconds{pipeline}
# - spine_dead_letters_total{pipeline}
# - spine_pipeline_runs_total{pipeline,result}
```

### Health Checks

```bash
# Liveness probe
curl http://localhost:8000/health/live

# Readiness probe (includes DB check)
curl http://localhost:8000/health/ready

# Full health with metrics
curl http://localhost:8000/health/metrics
```

### Structured Logging

All logs are JSON-formatted with correlation IDs:

```json
{
  "event": "pipeline_started",
  "pipeline": "otc_ingest",
  "execution_id": "abc-123",
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "info"
}
```

## Retention & Cleanup

A scheduled job runs to clean up old data:

```bash
# Manual cleanup
uv run spine cleanup --older-than 90d

# Cleanup runs automatically via Celery Beat (configurable)
```

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=market_spine --cov-report=html

# Run specific test categories
uv run pytest tests/test_api.py
uv run pytest tests/test_pipelines.py
uv run pytest tests/test_integration.py

# Run invariant tests
uv run pytest tests/test_invariants.py
```

## CI/CD

GitHub Actions workflow includes:

- **Lint**: Ruff linting and formatting checks
- **Type Check**: MyPy strict type checking
- **Unit Tests**: All unit and API tests
- **Integration Tests**: Docker Compose-based integration tests
- **Invariant Checks**: Architecture invariants enforcement

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection URL | Required |
| `REDIS_URL` | Redis connection URL | Required |
| `LOG_LEVEL` | Logging level | `INFO` |
| `METRICS_ENABLED` | Enable Prometheus metrics | `true` |
| `TRACING_ENABLED` | Enable OpenTelemetry tracing | `false` |
| `OTLP_ENDPOINT` | OpenTelemetry collector endpoint | `http://localhost:4317` |
| `RETENTION_DAYS` | Days to keep old executions | `90` |
| `MAX_RETRIES` | Max DLQ retry attempts | `3` |

## Project Structure

```
market-spine-full/
├── src/market_spine/
│   ├── api/              # FastAPI application
│   ├── core/             # Core domain: models, settings
│   ├── execution/        # Execution ledger, dispatcher
│   ├── backends/         # Task backends (Celery, stub for Temporal)
│   ├── pipelines/        # Pipeline definitions
│   ├── services/         # OTC connector, normalization
│   ├── repositories/     # Database access
│   ├── observability/    # Metrics, logging, tracing
│   ├── cli.py            # Typer CLI
│   └── celery_app.py     # Celery configuration
├── migrations/           # Database migrations
├── k8s/                  # Kubernetes manifests
├── tests/                # Test suite
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## License

MIT
