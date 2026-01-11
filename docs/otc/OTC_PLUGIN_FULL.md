# OTC Weekly Transparency Plugin — Full Tier

> **Target:** `market-spine-full`  
> **Builds on:** Advanced tier  
> **Prerequisites:** See [SHARED_MODELS.md](SHARED_MODELS.md) for common code

---

## 1. What Full Adds to Advanced

| Feature | Advanced | Full |
|---------|----------|------|
| Database | PostgreSQL | TimescaleDB (hypertables) |
| Aggregates | Manual queries | Continuous aggregates |
| Events | None | Event sourcing |
| Observability | Logging | OpenTelemetry + Prometheus |
| Deployment | Docker | Kubernetes |
| Retention | Manual | Automated policies |
| Gap detection | None | Built-in |

**Same Celery/Redis/S3 stack**, adds time-series optimization + observability.

---

## 2. Files to Create

```
market-spine-full/
├── migrations/
│   ├── 020_otc_tables.sql              # Modified for TimescaleDB
│   ├── 021_otc_rolling.sql             # Copy from Advanced
│   ├── 022_otc_concentration.sql       # Copy from Advanced
│   ├── 023_otc_hypertables.sql         # NEW: Convert to hypertables
│   ├── 024_otc_continuous_agg.sql      # NEW: Continuous aggregates
│   ├── 025_otc_retention.sql           # NEW: Retention policies
│   └── 026_otc_events.sql              # NEW: Event store
├── src/market_spine/
│   └── domains/
│       └── otc/
│           ├── __init__.py
│           ├── models.py               # Copy (same as all tiers)
│           ├── parser.py               # Copy (same)
│           ├── normalizer.py           # Copy (same)
│           ├── calculations.py         # Copy from Advanced
│           ├── connector.py            # Copy from Intermediate
│           ├── repository.py           # Copy from Intermediate
│           ├── quality.py              # Copy from Intermediate
│           ├── storage.py              # Copy from Advanced
│           ├── schedule.py             # Copy from Advanced
│           ├── events.py               # NEW: Event sourcing
│           ├── telemetry.py            # NEW: OpenTelemetry
│           ├── gaps.py                 # NEW: Gap detection
│           └── pipelines.py            # Modified for events/telemetry
└── k8s/
    └── otc/
        └── cronjob.yaml                # NEW: K8s CronJob
```

---

## 3. New: TimescaleDB Hypertables

```sql
-- migrations/023_otc_hypertables.sql

-- Convert venue_volume to hypertable (time-series optimized)
SELECT create_hypertable(
    'otc.venue_volume',
    'week_ending',
    chunk_time_interval => INTERVAL '4 weeks',
    if_not_exists => TRUE
);

-- Enable compression for older data
ALTER TABLE otc.venue_volume 
    SET (timescaledb.compress = true);

SELECT add_compression_policy('otc.venue_volume', INTERVAL '12 weeks');
```

---

## 4. New: Continuous Aggregates

```sql
-- migrations/024_otc_continuous_agg.sql

-- Pre-computed weekly summaries (refresh automatically)
CREATE MATERIALIZED VIEW otc.weekly_summary_agg
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 week', week_ending) AS week,
    symbol,
    tier,
    SUM(share_volume) AS total_volume,
    SUM(trade_count) AS total_trades,
    COUNT(DISTINCT venue) AS venue_count
FROM otc.venue_volume
GROUP BY 1, 2, 3
WITH NO DATA;

-- Refresh policy: refresh last 4 weeks every hour
SELECT add_continuous_aggregate_policy(
    'otc.weekly_summary_agg',
    start_offset => INTERVAL '4 weeks',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);
```

---

## 5. New: Retention Policies

```sql
-- migrations/025_otc_retention.sql

-- Keep venue_volume for 2 years
SELECT add_retention_policy(
    'otc.venue_volume',
    INTERVAL '104 weeks'
);

-- Keep raw_records for 6 months only
SELECT add_retention_policy(
    'otc.raw_record',
    INTERVAL '26 weeks'
);

-- Summaries kept indefinitely (much smaller)
```

---

## 6. New: Event Store

```sql
-- migrations/026_otc_events.sql

CREATE TABLE otc.events (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_events_aggregate 
    ON otc.events(aggregate_type, aggregate_id);

CREATE INDEX idx_events_type_time 
    ON otc.events(event_type, created_at);
```

---

## 7. New: Event Sourcing

```python
# src/market_spine/domains/otc/events.py

"""Event sourcing - Full tier adds this."""

import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import Any
import json


@dataclass
class OTCEvent:
    """Base event."""
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict
    created_at: datetime = None
    
    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.utcnow()


# Concrete events
@dataclass
class FileIngested(OTCEvent):
    """Emitted when a FINRA file is ingested."""
    event_type: str = "otc.file.ingested"
    aggregate_type: str = "otc.file"


@dataclass
class WeekNormalized(OTCEvent):
    """Emitted when a week's data is normalized."""
    event_type: str = "otc.week.normalized"
    aggregate_type: str = "otc.week"


@dataclass
class SummaryComputed(OTCEvent):
    """Emitted when summaries are computed."""
    event_type: str = "otc.summary.computed"
    aggregate_type: str = "otc.week"


class OTCEventStore:
    """
    Simple event store.
    
    In production, consider Kafka, EventStoreDB, etc.
    """
    
    def __init__(self, conn):
        self.conn = conn
    
    async def append(self, event: OTCEvent) -> None:
        """Store an event."""
        await self.conn.execute("""
            INSERT INTO otc.events 
                (event_id, event_type, aggregate_type, aggregate_id, payload, metadata)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, 
            event.event_id,
            event.event_type,
            event.aggregate_type,
            event.aggregate_id,
            json.dumps(event.payload),
            json.dumps({"created_at": event.created_at.isoformat()}),
        )
    
    async def get_events(
        self, 
        aggregate_type: str, 
        aggregate_id: str
    ) -> list[dict]:
        """Retrieve events for an aggregate."""
        rows = await self.conn.fetch("""
            SELECT * FROM otc.events
            WHERE aggregate_type = $1 AND aggregate_id = $2
            ORDER BY created_at
        """, aggregate_type, aggregate_id)
        return [dict(r) for r in rows]
```

---

## 8. New: Observability

```python
# src/market_spine/domains/otc/telemetry.py

"""OpenTelemetry instrumentation - Full tier adds this."""

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Histogram
from functools import wraps


# Prometheus metrics
OTC_FILES_INGESTED = Counter(
    "otc_files_ingested_total",
    "Total FINRA files ingested",
    ["tier"]
)

OTC_RECORDS_PARSED = Counter(
    "otc_records_parsed_total",
    "Total records parsed",
    ["tier", "status"]  # status: success, skipped, error
)

OTC_INGEST_DURATION = Histogram(
    "otc_ingest_duration_seconds",
    "Time to ingest a file",
    ["tier"],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60]
)

OTC_SUMMARY_DURATION = Histogram(
    "otc_summary_duration_seconds",
    "Time to compute summaries",
    buckets=[0.1, 0.5, 1, 5, 10]
)


# OpenTelemetry tracing
tracer = trace.get_tracer("market_spine.otc")


def traced(name: str):
    """Decorator to add tracing to functions."""
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(name) as span:
                try:
                    result = await fn(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator


# Usage in pipelines:
#
# @traced("otc.ingest")
# async def run_ingest_pipeline(file_path: str) -> IngestResult:
#     ...
```

---

## 9. New: Gap Detection

```python
# src/market_spine/domains/otc/gaps.py

"""Gap detection for missing weeks - Full tier adds this."""

from datetime import date, timedelta


async def detect_gaps(conn, tier: str) -> list[date]:
    """
    Find missing weeks in the database.
    
    Returns list of week_ending dates that should exist but don't.
    """
    # Get all weeks we have
    rows = await conn.fetch("""
        SELECT DISTINCT week_ending 
        FROM otc.venue_volume 
        WHERE tier = $1
        ORDER BY week_ending
    """, tier)
    
    if len(rows) < 2:
        return []
    
    existing = {row["week_ending"] for row in rows}
    first = min(existing)
    last = max(existing)
    
    # Generate expected weeks (every Friday)
    expected = set()
    current = first
    while current <= last:
        expected.add(current)
        current += timedelta(weeks=1)
    
    # Find gaps
    missing = sorted(expected - existing)
    return missing


async def alert_gaps(conn, tier: str) -> None:
    """Check for gaps and log/alert if found."""
    gaps = await detect_gaps(conn, tier)
    if gaps:
        # In Full tier, this would send to alerting system
        print(f"WARNING: Missing weeks for {tier}: {gaps}")
```

---

## 10. New: Kubernetes CronJob

```yaml
# k8s/otc/cronjob.yaml

apiVersion: batch/v1
kind: CronJob
metadata:
  name: otc-ingest-tier1
  namespace: market-spine
spec:
  schedule: "0 6 * * WED"  # 6am every Wednesday
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 3
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: otc-ingest
              image: market-spine:latest
              command:
                - python
                - -m
                - market_spine.cli
                - pipeline
                - run
                - otc.ingest
                - --tier=NMS Tier 1
              env:
                - name: DATABASE_URL
                  valueFrom:
                    secretKeyRef:
                      name: market-spine-secrets
                      key: database-url
                - name: S3_BUCKET
                  value: market-spine-data
              resources:
                requests:
                  memory: "256Mi"
                  cpu: "100m"
                limits:
                  memory: "512Mi"
                  cpu: "500m"
```

---

## 11. Modified: Pipelines with Events + Telemetry

```python
# Key changes to pipelines.py for Full tier:

from market_spine.domains.otc.events import OTCEventStore, FileIngested
from market_spine.domains.otc.telemetry import (
    traced, OTC_FILES_INGESTED, OTC_INGEST_DURATION
)


@traced("otc.ingest")
async def run_ingest_pipeline(file_path: str, tier: str) -> IngestResult:
    """
    Ingest with event sourcing and telemetry.
    """
    with OTC_INGEST_DURATION.labels(tier=tier).time():
        # ... same ingestion logic ...
        result = await _do_ingest(file_path, tier)
        
        # Emit event
        event = FileIngested(
            event_id=None,
            aggregate_id=f"{tier}/{result.week_ending}",
            payload={
                "file_path": file_path,
                "tier": tier,
                "rows_inserted": result.rows_inserted,
            },
        )
        await event_store.append(event)
        
        # Increment metrics
        OTC_FILES_INGESTED.labels(tier=tier).inc()
        
        return result
```

---

## 12. Tier Summary Table

| Feature | Basic | Intermediate | Advanced | Full |
|---------|-------|--------------|----------|------|
| Database | SQLite | PostgreSQL | PostgreSQL | TimescaleDB |
| API | CLI | + REST | + Celery | + Events |
| Storage | File | + HTTP | + S3 | + Compression |
| Scheduling | Manual | Manual | Celery Beat | + K8s CronJob |
| Calculations | Summaries | + Quality | + Rolling/HHI | + Continuous Agg |
| Observability | Print | Logging | Logging | OTEL + Prometheus |
| Retention | Manual | Manual | Manual | Automated |
| Gap detection | None | None | None | Built-in |

---

## 13. Quick Reference: What to Copy

| From | To Full |
|------|---------|
| SHARED_MODELS.md | models.py, parser.py, normalizer.py |
| Intermediate | connector.py, repository.py, quality.py |
| Advanced | calculations.py, storage.py, schedule.py |
| **New in Full** | events.py, telemetry.py, gaps.py, hypertables, k8s |
