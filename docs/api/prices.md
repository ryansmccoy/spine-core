# Price API Reference

> External market data prices from Alpha Vantage (and other sources).

## Base URL

```
/v1/data/prices
```

## Authentication

All endpoints require a valid API token passed via `Authorization: Bearer <token>` header.

---

## Endpoints

### GET /v1/data/prices/metadata

Returns metadata about available price captures, including capture IDs for as-of queries.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Filter by symbol (optional) |

**Response:**

```json
{
  "captures": [
    {
      "capture_id": "market_data.prices.AAPL.20240115T120000Z.abc12345",
      "captured_at": "2024-01-15T12:00:00Z",
      "symbol": "AAPL",
      "row_count": 100,
      "source": "alpha_vantage"
    }
  ]
}
```

**Example:**

```bash
curl -X GET "http://localhost:8000/v1/data/prices/metadata?symbol=AAPL" \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /v1/data/prices/{symbol}

Returns historical daily prices for a symbol with pagination and optional as-of filtering.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Stock symbol (e.g., AAPL, MSFT) |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `offset` | int | 0 | Pagination offset (0-based) |
| `limit` | int | 100 | Page size (max: 1000) |
| `start_date` | string | — | ISO date, filter by date >= start_date |
| `end_date` | string | — | ISO date, filter by date <= end_date |
| `capture_id` | string | — | Return data from specific capture (as-of query) |

**Response:**

```json
{
  "data": [
    {
      "symbol": "AAPL",
      "date": "2024-01-15",
      "open": 150.00,
      "high": 152.50,
      "low": 149.25,
      "close": 151.75,
      "volume": 10000000,
      "change": 2.00,
      "change_percent": 0.0134
    }
  ],
  "pagination": {
    "offset": 0,
    "limit": 100,
    "total": 250,
    "has_more": true
  },
  "capture": {
    "capture_id": "market_data.prices.AAPL.20240115T120000Z.abc12345",
    "captured_at": "2024-01-15T12:00:00Z"
  }
}
```

**Examples:**

```bash
# Basic query
curl -X GET "http://localhost:8000/v1/data/prices/AAPL" \
  -H "Authorization: Bearer $TOKEN"

# With pagination
curl -X GET "http://localhost:8000/v1/data/prices/AAPL?offset=100&limit=50" \
  -H "Authorization: Bearer $TOKEN"

# Date range
curl -X GET "http://localhost:8000/v1/data/prices/AAPL?start_date=2024-01-01&end_date=2024-01-31" \
  -H "Authorization: Bearer $TOKEN"

# As-of query (point-in-time)
curl -X GET "http://localhost:8000/v1/data/prices/AAPL?capture_id=market_data.prices.AAPL.20240115T120000Z.abc12345" \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /v1/data/prices/{symbol}/latest

Returns the most recent price for a symbol.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Stock symbol |

**Response:**

```json
{
  "symbol": "AAPL",
  "date": "2024-01-15",
  "open": 150.00,
  "high": 152.50,
  "low": 149.25,
  "close": 151.75,
  "volume": 10000000,
  "change": 2.00,
  "change_percent": 0.0134,
  "capture_id": "market_data.prices.AAPL.20240115T120000Z.abc12345",
  "captured_at": "2024-01-15T12:00:00Z"
}
```

**Example:**

```bash
curl -X GET "http://localhost:8000/v1/data/prices/AAPL/latest" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Error Responses

All errors follow a consistent format:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "No price data found for symbol: UNKNOWN"
  }
}
```

### Common Error Codes

| Status | Code | Description |
|--------|------|-------------|
| 400 | INVALID_REQUEST | Invalid parameters |
| 404 | NOT_FOUND | Symbol or capture not found |
| 422 | VALIDATION_ERROR | Parameter validation failed |
| 429 | RATE_LIMITED | Too many requests |
| 500 | INTERNAL_ERROR | Server error |

---

## As-Of Queries (Point-in-Time)

The Price API supports **as-of queries** for reproducibility and audit compliance.

### How It Works

1. Each data ingestion creates a unique `capture_id`
2. All rows from that ingestion share the same `capture_id`
3. Querying with `capture_id` returns exactly what was known at that time
4. Old captures are never deleted (append-only)

### Use Cases

- **Backtesting**: Query prices as they were known on a specific date
- **Auditing**: Reproduce exactly what data drove a decision
- **Debugging**: Compare current vs historical data captures

### Content Hash

Each capture includes a content hash suffix (first 8 chars of SHA-256). This ensures:

- Identical data fetched twice produces the same hash
- Changed data produces a different capture_id
- Idempotent ingestion (no duplicate captures for unchanged data)

---

## Rate Limiting

- Default: 100 requests per minute per API key
- Bulk operations should use pagination, not parallel requests
- Use `offset`/`limit` for large datasets

---

## Data Sources

Currently supported:

| Source | Type | Update Frequency |
|--------|------|------------------|
| Alpha Vantage | External API | Daily (compact) or Historical (full) |

### Source Metadata

Each price row includes:

- `source`: Data source identifier (e.g., "alpha_vantage")
- `capture_id`: Unique capture identifier
- `captured_at`: When the data was captured

---

## Frontend Integration

### Fetching Price History

```typescript
async function fetchPriceHistory(symbol: string, options?: {
  offset?: number;
  limit?: number;
  startDate?: string;
  endDate?: string;
}): Promise<PriceResponse> {
  const params = new URLSearchParams({
    offset: String(options?.offset ?? 0),
    limit: String(options?.limit ?? 100),
  });
  
  if (options?.startDate) params.append('start_date', options.startDate);
  if (options?.endDate) params.append('end_date', options.endDate);
  
  const response = await fetch(
    `/v1/data/prices/${symbol}?${params}`,
    { headers: { 'Authorization': `Bearer ${token}` } }
  );
  
  return response.json();
}
```

### Pagination Handling

```typescript
async function* fetchAllPrices(symbol: string) {
  let offset = 0;
  const limit = 100;
  
  while (true) {
    const response = await fetchPriceHistory(symbol, { offset, limit });
    
    yield* response.data;
    
    if (!response.pagination.has_more) break;
    offset += limit;
  }
}
```
