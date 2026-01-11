# Pricing Domain Architecture

> Market data pricing domain: sources, pipelines, and schemas.

## Overview

The `market_data` pricing domain handles external market data ingestion, storage, and querying. It follows the spine-core registry pattern while maintaining domain-specific semantics.

## Domain Structure

```
packages/spine-domains/src/spine/domains/market_data/
├── __init__.py              # Domain registration
├── sources/
│   ├── __init__.py          # Source factory and registry
│   ├── alpha_vantage.py     # Alpha Vantage source implementation
│   └── base.py              # BaseSource protocol
├── pipelines.py             # Ingestion pipelines
└── schema/
    ├── 00_tables.sql        # Table definitions
    ├── 01_indexes.sql       # Performance indexes
    └── 02_views.sql         # Analytical views
```

## Core Concepts

### Sources

Sources fetch data from external APIs. Each source:

1. **Implements fetch protocol**: `fetch(params) -> FetchResult`
2. **Returns structured result**: Data, anomalies, metadata
3. **Handles retries**: Exponential backoff for rate limits
4. **Computes content hash**: SHA-256 for deduplication

```python
from spine.domains.market_data.sources import create_source, FetchResult

source = create_source(source_type="alpha_vantage")
result: FetchResult = source.fetch({"symbol": "AAPL", "outputsize": "compact"})

if result.success:
    print(f"Fetched {len(result.data)} rows")
    print(f"Content hash: {result.metadata.content_hash}")
else:
    print(f"Anomalies: {result.anomalies}")
```

### FetchResult

```python
@dataclass
class FetchResult:
    """Result from source fetch operation."""
    data: list[dict[str, Any]]      # Normalized price rows
    anomalies: list[dict[str, Any]] # Issues encountered
    metadata: SourceMetadata | None  # Fetch metadata
    success: bool                    # Overall success
```

### SourceMetadata

```python
@dataclass
class SourceMetadata:
    """Metadata about a fetch operation."""
    source_type: str           # e.g., "alpha_vantage"
    source_uri: str            # API endpoint
    fetched_at: datetime       # When fetched
    content_hash: str          # SHA-256 of response
    etag: str | None           # HTTP ETag if available
    last_modified: str | None  # HTTP Last-Modified
    response_size_bytes: int   # Response size
    request_params_hash: str   # Hash of request params
```

### Pipelines

Pipelines orchestrate data flow from source to database:

```python
from spine.domains.market_data.pipelines import IngestPricesPipeline

pipeline = IngestPricesPipeline(
    symbol="AAPL",
    source_type="alpha_vantage",
    outputsize="compact",
)

result = pipeline.run(conn)
print(f"Captured: {result.capture_id}")
```

#### Batch Pipeline

For multiple symbols with rate limiting:

```python
from spine.domains.market_data.pipelines import IngestPricesBatchPipeline

pipeline = IngestPricesBatchPipeline(
    symbols=["AAPL", "MSFT", "GOOGL"],
    source_type="alpha_vantage",
    sleep_between=12.0,  # 5 req/min = 12s between
)

results = pipeline.run(conn)
```

### Schema

#### Tables

```sql
CREATE TABLE market_data_prices_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    change REAL,
    change_percent REAL,
    source TEXT,
    capture_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    is_valid INTEGER DEFAULT 1,
    UNIQUE(symbol, date, capture_id)
);
```

#### Key Indexes

```sql
-- Latest capture lookup
CREATE INDEX idx_prices_capture_id ON market_data_prices_daily(capture_id);

-- Time-ordered queries
CREATE INDEX idx_prices_captured_at ON market_data_prices_daily(captured_at DESC);

-- Symbol + date range
CREATE INDEX idx_prices_symbol_date ON market_data_prices_daily(symbol, date DESC);
```

## Capture Semantics

### Capture ID Format

```
market_data.prices.{symbol}.{timestamp}.{content_hash_prefix}
```

Example: `market_data.prices.AAPL.20240115T120000Z.abc12345`

### Append-Only Model

- **No updates**: Each fetch creates a new capture
- **No deletes**: Old data preserved for as-of queries
- **Content-addressed**: Same data = same hash suffix
- **Audit trail**: Complete history of all ingestions

### As-Of Queries

Query data as it was known at a specific capture:

```sql
SELECT * FROM market_data_prices_daily
WHERE symbol = 'AAPL'
  AND capture_id = 'market_data.prices.AAPL.20240115T120000Z.abc12345'
ORDER BY date DESC;
```

## Change Calculation

Pipelines calculate daily changes when not provided:

```python
def calculate_changes(data: list[dict]) -> list[dict]:
    """Add change and change_percent to each row."""
    sorted_data = sorted(data, key=lambda x: x["date"])
    
    for i, row in enumerate(sorted_data):
        if i == 0:
            row["change"] = None
            row["change_percent"] = None
        else:
            prev_close = sorted_data[i - 1]["close"]
            row["change"] = row["close"] - prev_close
            row["change_percent"] = row["change"] / prev_close if prev_close else None
    
    return sorted_data
```

## Error Handling

### Anomaly Categories

| Category | Description |
|----------|-------------|
| `api_error` | API returned error message |
| `rate_limit` | Rate limit exceeded (429) |
| `network_error` | Connection or timeout |
| `parse_error` | Response parsing failed |
| `validation_error` | Data validation failed |

### Retry Strategy

```python
MAX_RETRIES = 3
BACKOFF_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff

for attempt in range(MAX_RETRIES):
    result = fetch_with_retry(params)
    if result.success:
        break
    time.sleep(BACKOFF_DELAYS[attempt])
```

## Registry Integration

The domain registers with spine-core's registry:

```python
# In __init__.py
from spine.framework.registry import Registry

Registry.register_domain("market_data", {
    "sources": ["alpha_vantage"],
    "pipelines": ["ingest_prices", "ingest_prices_batch"],
    "schemas": ["00_tables.sql", "01_indexes.sql", "02_views.sql"],
})
```

## Testing

### Unit Tests

```bash
pytest packages/spine-domains/tests/market_data/test_alpha_vantage.py -v
```

### Integration Tests

```bash
pytest market-spine-basic/tests/test_prices_integration.py -v
```

### Smoke Tests

```bash
python scripts/smoke_prices.py --base-url http://localhost:8000 --symbol AAPL
```

## Scheduled Ingestion

Use the scheduler script for cron/container orchestration:

```bash
# Ingest multiple symbols
python scripts/run_price_schedule.py --symbols AAPL,MSFT,GOOGL --mode run

# Dry run (no database writes)
python scripts/run_price_schedule.py --symbols AAPL --mode dry-run

# From file with rate limiting
python scripts/run_price_schedule.py \
  --symbols-file watchlist.txt \
  --sleep-between 12 \
  --max-symbols-per-batch 25
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ALPHA_VANTAGE_API_KEY` | API key for Alpha Vantage | Required |
| `MARKET_SPINE_DB_PATH` | Database file path | `spine.db` |
| `MARKET_DATA_SOURCE` | Default source type | `alpha_vantage` |

### Rate Limits

| Source | Free Tier | Premium |
|--------|-----------|---------|
| Alpha Vantage | 5 req/min, 25/day | 75 req/min |

Default `sleep_between=12.0` ensures free tier compliance.
