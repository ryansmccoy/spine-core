# API Design Guardrails

> Canonical rules for designing spine-core APIs. Reference this prompt when creating or modifying API endpoints.

## Core Principles

### 1. Resource-Style URLs

**DO:**
```
GET  /v1/data/prices/{symbol}
GET  /v1/data/prices/{symbol}/latest
GET  /v1/otc/{tier}/{week}/summary
POST /v1/otc/{tier}/{week}/compare
```

**DON'T:**
```
GET  /v1/getPrices?symbol=AAPL
POST /v1/api/execute/price-query
GET  /v1/data?type=prices&symbol=AAPL
```

### 2. Consistent Naming

- **Plural nouns** for collections: `prices`, `captures`, `symbols`
- **Lowercase with hyphens** for multi-word: `change-percent`, not `changePercent`
- **Path segments** for hierarchy: `/otc/{tier}/{week}`, not query params
- **Query params** for filtering: `?start_date=2024-01-01`

### 3. HTTP Methods

| Method | Purpose | Idempotent |
|--------|---------|------------|
| GET | Read/query data | Yes |
| POST | Create resource or complex query | No |
| PUT | Full update | Yes |
| PATCH | Partial update | No |
| DELETE | Remove resource | Yes |

**Rule:** If an operation is read-only but requires complex parameters, use POST with a body.

### 4. Pagination

**Always paginate** collections that can grow unbounded:

```json
{
  "data": [...],
  "pagination": {
    "offset": 0,
    "limit": 100,
    "total": 1234,
    "has_more": true
  }
}
```

**Parameters:**
- `offset`: 0-based starting position
- `limit`: Page size (default: 100, max: 1000)
- `total`: Total count (if computable efficiently)
- `has_more`: Boolean for "next page exists"

### 5. Response Envelope

**Standard success:**
```json
{
  "data": {...},
  "pagination": {...},
  "meta": {...}
}
```

**Standard error:**
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Resource not found",
    "details": {...}
  }
}
```

### 6. Versioning

- **URL prefix**: `/v1/`, `/v2/`
- **Never break backward compatibility** within a version
- **Deprecate, don't remove** endpoints

---

## Domain-Specific Patterns

### OTC Domain (FINRA data)

Uses tier/week partitioning reflecting data structure:

```
/v1/otc/{tier}/{week}/...

tier: tier1, tier2, otc
week: 20251215 (YYYYMMDD format)
```

**Rationale:** FINRA publishes weekly by tier; API mirrors this.

### Market Data (External APIs)

Uses resource-style endpoints:

```
/v1/data/prices/{symbol}
/v1/data/prices/{symbol}/latest
/v1/data/prices/metadata
```

**Rationale:** External data doesn't have tier/week structure.

---

## As-Of Queries

For audit and reproducibility, support point-in-time queries:

```
GET /v1/data/prices/AAPL?capture_id=market_data.prices.AAPL.20240115T120000Z.abc12345
```

**Include in response:**
```json
{
  "capture": {
    "capture_id": "...",
    "captured_at": "2024-01-15T12:00:00Z"
  }
}
```

---

## Query Parameter Standards

| Purpose | Parameter | Example |
|---------|-----------|---------|
| Pagination | `offset`, `limit` | `?offset=100&limit=50` |
| Date filtering | `start_date`, `end_date` | `?start_date=2024-01-01` |
| Point-in-time | `capture_id` | `?capture_id=...` |
| Sorting | `sort`, `order` | `?sort=date&order=desc` |
| Field selection | `fields` | `?fields=symbol,close` |

---

## Guardrails for LLMs

When generating or modifying API endpoints:

1. ✅ Check existing patterns in `docs/api/` before creating new ones
2. ✅ Use resource nouns, not verbs
3. ✅ Include pagination for list endpoints
4. ✅ Support `capture_id` for as-of queries where applicable
5. ✅ Return consistent error structure
6. ❌ Don't mix query styles (RPC vs REST) in same domain
7. ❌ Don't expose internal IDs (use `capture_id` instead of `row_id`)
8. ❌ Don't require Pydantic in domain layer (use dataclasses)
9. ❌ Don't modify spine-core without explicit approval

---

## Checklist

Before submitting API changes:

- [ ] Follows resource-style URL pattern
- [ ] Uses correct HTTP method
- [ ] Includes pagination for collections
- [ ] Supports as-of queries where appropriate
- [ ] Has consistent response envelope
- [ ] Error responses follow standard format
- [ ] Documented in `docs/api/`
- [ ] Has smoke test in `scripts/smoke_*.py`
