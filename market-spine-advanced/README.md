# Market Spine Advanced

Advanced tier of the Market Spine analytics pipeline system featuring:

- **Celery Backend**: Distributed task execution with Redis broker
- **Dead Letter Queue (DLQ)**: Failed execution handling with automatic retry
- **External API Ingestion**: HTTP client for pulling data from market data APIs
- **File Storage Abstraction**: Local filesystem and S3-compatible object storage
- **Scheduling**: Celery Beat for periodic/cron-based pipeline execution
- **FastAPI REST API**: Full execution management and data querying

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   FastAPI       │────▶│   PostgreSQL    │◀────│  Celery Worker  │
│   (Enqueue)     │     │   (State)       │     │  (Execute)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │                        │
                               │                        ▼
                               │                ┌─────────────────┐
                               │                │     Redis       │
                               │                │   (Broker)      │
                               └───────────────▶└─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │  Celery Beat    │
                                                │  (Scheduler)    │
                                                └─────────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.12+
- uv (Python package manager)

### Development Setup

```bash
# Start infrastructure
docker-compose up -d db redis

# Install dependencies
uv sync

# Initialize database
uv run spine db init

# Start worker (in separate terminal)
uv run spine worker

# Start scheduler (in separate terminal)
uv run spine scheduler

# Start API
uv run spine serve
```

### Docker Compose (Full Stack)

```bash
docker-compose up -d
```

## Features

### External API Ingestion

```bash
# Pull data from configured market data API
uv run spine pipeline run otc.fetch --date 2024-01-15

# Or via API
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{"pipeline_name": "otc.fetch", "params": {"date": "2024-01-15"}}'
```

### File Storage

Configurable storage backends:
- **Local**: Files stored on local filesystem
- **S3**: S3-compatible object storage (AWS S3, MinIO, etc.)

```python
from market_spine.storage import get_storage

storage = get_storage()
storage.write("data/trades/2024-01-15.csv", content)
content = storage.read("data/trades/2024-01-15.csv")
```

### Scheduling

Define periodic tasks in configuration:

```python
# Scheduled via Celery Beat
CELERY_BEAT_SCHEDULE = {
    "daily-otc-fetch": {
        "task": "market_spine.tasks.run_pipeline",
        "schedule": crontab(hour=6, minute=0),  # 6 AM daily
        "args": ["otc.fetch", {}],
    },
    "hourly-metrics-compute": {
        "task": "market_spine.tasks.run_pipeline", 
        "schedule": crontab(minute=0),  # Every hour
        "args": ["otc.compute", {}],
    },
}
```

### Dead Letter Queue

Failed executions are automatically moved to DLQ:

```bash
# List DLQ executions
uv run spine dlq list

# Retry a failed execution (creates new execution with parent link)
uv run spine dlq retry <execution_id>

# Retry all DLQ items
uv run spine dlq retry-all
```

## CLI Commands

```bash
spine --help                    # Show all commands
spine db init                   # Initialize database
spine pipeline list             # List available pipelines
spine pipeline run <name>       # Run pipeline synchronously
spine pipeline submit <name>    # Submit for async execution
spine worker                    # Start Celery worker
spine scheduler                 # Start Celery Beat scheduler
spine serve                     # Start API server
spine dlq list                  # List DLQ executions
spine dlq retry <id>            # Retry failed execution
spine schedule list             # List scheduled tasks
spine schedule add              # Add scheduled task
```

## API Endpoints

### Executions
- `POST /api/v1/executions` - Submit execution
- `GET /api/v1/executions` - List executions
- `GET /api/v1/executions/{id}` - Get execution details
- `POST /api/v1/executions/{id}/cancel` - Cancel execution

### DLQ
- `GET /api/v1/dlq` - List DLQ executions
- `POST /api/v1/dlq/{id}/retry` - Retry execution
- `POST /api/v1/dlq/retry-all` - Retry all

### Schedules
- `GET /api/v1/schedules` - List schedules
- `POST /api/v1/schedules` - Create schedule
- `DELETE /api/v1/schedules/{id}` - Delete schedule

### OTC Data
- `GET /api/v1/otc/symbols` - List symbols
- `GET /api/v1/otc/trades` - List trades
- `GET /api/v1/otc/metrics` - List metrics
- `POST /api/v1/otc/pipelines/fetch` - Trigger data fetch

## Configuration

Environment variables (`.env`):

```bash
# Database
DATABASE_URL=postgresql://spine:password@localhost:5432/market_spine

# Redis
REDIS_URL=redis://localhost:6379/0

# Backend
BACKEND_TYPE=celery

# Storage
STORAGE_TYPE=local  # or "s3"
STORAGE_LOCAL_PATH=./data
STORAGE_S3_BUCKET=market-spine-data
STORAGE_S3_ENDPOINT=http://localhost:9000  # For MinIO

# External APIs
OTC_API_BASE_URL=https://api.example.com/otc
OTC_API_KEY=your-api-key

# Scheduling
SCHEDULER_ENABLED=true
```

## Project Structure

```
market-spine-advanced/
├── src/market_spine/
│   ├── api/                 # FastAPI application
│   │   └── routes/
│   ├── orchestration/       # Execution backends
│   │   ├── backends/
│   │   │   ├── protocol.py
│   │   │   ├── local.py
│   │   │   └── celery.py
│   │   ├── scheduler.py
│   │   └── dlq.py
│   ├── storage/             # File storage abstraction
│   │   ├── base.py
│   │   ├── local.py
│   │   └── s3.py
│   ├── connectors/          # External API clients
│   │   └── otc_api.py
│   ├── repositories/
│   ├── services/
│   ├── pipelines/
│   ├── tasks.py             # Celery tasks
│   ├── celery_app.py        # Celery configuration
│   └── cli.py
├── migrations/
├── tests/
├── docker-compose.yml
└── pyproject.toml
```
