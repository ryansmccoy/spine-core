# Pricing Domain Playbook

> Step-by-step guide for working with the market_data pricing domain. Reference this when implementing price-related features.

## Quick Reference

### Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                             │
│  market-spine-basic/src/market_spine/api/routes/v1/prices.py│
│  - FastAPI endpoints                                         │
│  - Pydantic models (boundary only)                          │
│  - HTTP status codes                                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Command Layer                           │
│  market-spine-basic/src/market_spine/app/commands/prices.py │
│  - Dataclass commands (NOT Pydantic)                        │
│  - Business logic                                            │
│  - Guardrails (MAX_LIMIT, MAX_DAYS)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Domain Layer                            │
│  packages/spine-domains/src/spine/domains/market_data/      │
│  - Sources (alpha_vantage.py)                               │
│  - Pipelines (pipelines.py)                                 │
│  - Schema (schema/*.sql)                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Framework Layer                         │
│  packages/spine-core/src/spine/framework/                   │
│  - DO NOT MODIFY                                            │
│  - Registry, DB connections, base classes                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Common Tasks

### 1. Adding a New Data Source

**Location:** `packages/spine-domains/src/spine/domains/market_data/sources/`

**Steps:**

1. Create new source file (e.g., `yahoo_finance.py`)
2. Implement the source protocol:

```python
from dataclasses import dataclass
from typing import Any
from .base import FetchResult, SourceMetadata

@dataclass
class YahooFinanceSource:
    """Yahoo Finance data source."""
    
    def fetch(self, params: dict[str, Any]) -> FetchResult:
        symbol = params["symbol"]
        # Implement fetch logic
        return FetchResult(
            data=[...],
            anomalies=[],
            metadata=SourceMetadata(...),
            success=True,
        )
```

3. Register in `sources/__init__.py`:

```python
from .yahoo_finance import YahooFinanceSource

SOURCE_REGISTRY = {
    "alpha_vantage": AlphaVantageSource,
    "yahoo_finance": YahooFinanceSource,
}
```

4. Add tests in `packages/spine-domains/tests/market_data/test_yahoo_finance.py`

---

### 2. Adding a New Endpoint

**Location:** `market-spine-basic/src/market_spine/api/routes/v1/prices.py`

**Steps:**

1. Create command in `app/commands/prices.py`:

```python
@dataclass
class QueryPriceStatsCommand:
    """Query price statistics for a symbol."""
    symbol: str
    days: int = 30
    
    MAX_DAYS: ClassVar[int] = 365
    
    def execute(self) -> dict:
        # Implementation
        pass
```

2. Add endpoint in `routes/v1/prices.py`:

```python
@router.get("/{symbol}/stats")
async def get_price_stats(
    symbol: str,
    days: int = Query(default=30, ge=1, le=365),
) -> PriceStatsResponse:
    command = QueryPriceStatsCommand(symbol=symbol, days=days)
    return command.execute()
```

3. Add response model (Pydantic, boundary only):

```python
class PriceStatsResponse(BaseModel):
    symbol: str
    avg_close: float
    min_close: float
    max_close: float
    volatility: float
```

4. Document in `docs/api/prices.md`
5. Add smoke test in `scripts/smoke_prices.py`

---

### 3. Modifying Schema

**Location:** `packages/spine-domains/src/spine/domains/market_data/schema/`

**Steps:**

1. Add new migration file (numbered):

```sql
-- 03_add_stats_table.sql
CREATE TABLE IF NOT EXISTS market_data_price_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    period TEXT NOT NULL,
    avg_close REAL,
    volatility REAL,
    calculated_at TEXT NOT NULL,
    UNIQUE(symbol, period)
);
```

2. Add index if needed in `01_indexes.sql`:

```sql
CREATE INDEX IF NOT EXISTS idx_stats_symbol 
ON market_data_price_stats(symbol);
```

3. Update `ensure_schema()` in `pipelines.py` if needed

---

### 4. Adding Batch Ingestion

**Location:** `packages/spine-domains/src/spine/domains/market_data/pipelines.py`

**Use existing `IngestPricesBatchPipeline`:**

```python
from spine.domains.market_data.pipelines import IngestPricesBatchPipeline

pipeline = IngestPricesBatchPipeline(
    symbols=["AAPL", "MSFT", "GOOGL"],
    source_type="alpha_vantage",
    sleep_between=12.0,  # Rate limit compliance
)

results = pipeline.run(conn)
for r in results:
    print(f"{r.symbol}: {r.rows_inserted} rows, capture_id={r.capture_id}")
```

---

## Key Patterns

### Content Hash for Deduplication

```python
import hashlib
import json

def compute_content_hash(data: dict) -> str:
    """Deterministic hash of response data."""
    canonical = json.dumps(data, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
```

### Capture ID Format

```
{domain}.{entity}.{symbol}.{timestamp}.{content_hash_prefix}
```

Example: `market_data.prices.AAPL.20240115T120000Z.abc12345`

### As-Of Query Pattern

```python
def query_as_of(conn, symbol: str, capture_id: str | None) -> list:
    if capture_id:
        query = """
            SELECT * FROM market_data_prices_daily
            WHERE symbol = ? AND capture_id = ?
            ORDER BY date DESC
        """
        return conn.execute(query, (symbol, capture_id)).fetchall()
    else:
        # Latest capture
        query = """
            SELECT * FROM market_data_prices_daily
            WHERE symbol = ? AND capture_id = (
                SELECT capture_id FROM market_data_prices_daily
                WHERE symbol = ?
                ORDER BY captured_at DESC
                LIMIT 1
            )
            ORDER BY date DESC
        """
        return conn.execute(query, (symbol, symbol)).fetchall()
```

---

## Testing Checklist

### Unit Tests

```bash
# Source tests
pytest packages/spine-domains/tests/market_data/test_alpha_vantage.py -v

# Mock external APIs, test:
# - FetchResult structure
# - Content hash computation
# - Retry logic
# - Error handling
```

### Integration Tests

```bash
# API tests
pytest market-spine-basic/tests/test_prices_integration.py -v

# Test:
# - Pagination
# - As-of queries
# - Error responses
```

### Smoke Tests

```bash
# End-to-end
python scripts/smoke_prices.py --base-url http://localhost:8000 --symbol AAPL

# Tests:
# - Server health
# - All endpoints reachable
# - Response structure
```

---

## Debugging

### Check Database State

```bash
sqlite3 spine.db

-- Recent captures
SELECT capture_id, COUNT(*) as rows, MIN(date), MAX(date)
FROM market_data_prices_daily
GROUP BY capture_id
ORDER BY capture_id DESC
LIMIT 10;

-- Check for anomalies
SELECT * FROM anomalies ORDER BY recorded_at DESC LIMIT 20;
```

### Check Logs

```bash
# Scheduler logs
python scripts/run_price_schedule.py --symbols AAPL --mode dry-run --log-level DEBUG
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Empty data | No API key | Set `ALPHA_VANTAGE_API_KEY` |
| Rate limit | Too fast | Increase `sleep_between` |
| Duplicate captures | Same content | Expected (content hash dedup) |
| Missing schema | Not initialized | Run `ensure_schema()` |

---

## Non-Negotiable Rules

1. **DO NOT modify spine-core** - Framework layer is frozen
2. **Dataclasses in domain/command layer** - Not Pydantic
3. **Pydantic at API boundary only** - For request/response validation
4. **Append-only data** - Never delete, use capture_id for versioning
5. **Content hash in capture_id** - For deduplication
6. **Parameterized SQL** - Never string interpolation
7. **MAX_LIMIT=1000** - Hard cap on page size
8. **MAX_DAYS=365** - Hard cap on date range

---

## File Quick Reference

| Purpose | File |
|---------|------|
| API endpoints | `market-spine-basic/.../api/routes/v1/prices.py` |
| Commands | `market-spine-basic/.../app/commands/prices.py` |
| Source (fetch) | `packages/spine-domains/.../sources/alpha_vantage.py` |
| Pipeline (ingest) | `packages/spine-domains/.../pipelines.py` |
| Schema | `packages/spine-domains/.../schema/*.sql` |
| Scheduler | `scripts/run_price_schedule.py` |
| Smoke test | `scripts/smoke_prices.py` |
| API docs | `docs/api/prices.md` |
| Domain docs | `docs/domains/pricing.md` |
