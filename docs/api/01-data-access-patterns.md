# Data Access Patterns

> Last Updated: 2026-01-04  
> Version: 1.0  
> Status: **AUTHORITATIVE**

This document defines the standard patterns for querying domain data through the Market Spine API.

---

## 1. Query Semantics

### Latest vs As-Of

Market Spine supports two query modes:

| Mode | Use Case | How to Request |
|------|----------|----------------|
| **Latest** | Get current/most recent data | Default (no `capture_id` param) |
| **As-Of** | Point-in-time replay | Provide `capture_id` parameter |

#### Latest Queries

Latest queries return the most recent *ready* data for a partition:

```
GET /v1/data/calcs/weekly_symbol_volume_by_tier_v1?tier=NMS_TIER_1&week=2025-12-22
```

The response includes metadata about which capture was used:

```json
{
  "calc_name": "weekly_symbol_volume_by_tier_v1",
  "calc_version": "v1",
  "query_time": "2026-01-04T15:30:00Z",
  "capture": {
    "capture_id": "finra.otc_transparency:NMS_TIER_1:2025-12-22:20251223",
    "captured_at": "2025-12-23T10:00:00Z",
    "is_latest": true
  },
  "rows": [...]
}
```

#### As-Of Queries

As-of queries return data exactly as it existed at a specific capture:

```
GET /v1/data/calcs/weekly_symbol_volume_by_tier_v1?capture_id=finra.otc_transparency:NMS_TIER_1:2025-12-22:20251222
```

The response indicates whether this is the latest capture:

```json
{
  "calc_name": "weekly_symbol_volume_by_tier_v1",
  "calc_version": "v1",
  "query_time": "2026-01-04T15:30:00Z",
  "capture": {
    "capture_id": "finra.otc_transparency:NMS_TIER_1:2025-12-22:20251222",
    "captured_at": "2025-12-22T10:00:00Z",
    "is_latest": false,
    "latest_capture_id": "finra.otc_transparency:NMS_TIER_1:2025-12-22:20251223"
  },
  "rows": [...]
}
```

### Version Selection

Calcs are versioned. Clients can request:

| Request | Behavior |
|---------|----------|
| `/calcs/venue_share_v1` | Explicit version (recommended) |
| `/calcs/venue_share` | Latest non-deprecated version (convenience) |

**Recommendation**: Always use explicit versions in production code for reproducibility.

---

## 2. Common Filters

### Standard Query Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `tier` | string | FINRA tier code | `NMS_TIER_1`, `NMS_TIER_2`, `OTC` |
| `week` | string | Week ending date (YYYY-MM-DD) | `2025-12-22` |
| `symbol` | string | Trading symbol | `AAPL` |
| `symbols` | string[] | Multiple symbols (comma-separated) | `AAPL,MSFT,GOOGL` |
| `venue` | string | MPID venue code | `NSDQ`, `ARCX` |
| `capture_id` | string | Specific capture for as-of query | `finra.otc_transparency:...` |
| `limit` | int | Max rows to return | `100` (default: 50) |
| `offset` | int | Skip N rows (for pagination) | `50` |

### Filter Validation

Invalid filter values return `400 Bad Request`:

```json
{
  "error": {
    "code": "INVALID_TIER",
    "message": "Unknown tier 'TIER_X'. Valid values: NMS_TIER_1, NMS_TIER_2, OTC",
    "details": {
      "parameter": "tier",
      "provided": "TIER_X",
      "valid_values": ["NMS_TIER_1", "NMS_TIER_2", "OTC"]
    }
  }
}
```

---

## 3. Pagination

### Design Decision: Offset-Based Pagination

Market Spine uses **offset-based pagination** for simplicity and debuggability.

| Approach | Pros | Cons | Our Choice |
|----------|------|------|------------|
| **Offset** | Simple, debuggable, random access | O(n) skip cost, drift on updates | ✓ Chosen |
| **Cursor** | O(1) skip, stable during updates | Opaque, forward-only, complex | Future consideration |

**Rationale**: 
- Most queries return small result sets (< 1000 rows)
- Data is immutable within a capture (no drift concern for as-of queries)
- Offset is familiar to SQL users and easy to debug

### Pagination Parameters

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `limit` | int | 50 | 1000 | Rows per page |
| `offset` | int | 0 | — | Starting position |

### Pagination Metadata

All list responses include pagination metadata:

```json
{
  "rows": [...],
  "pagination": {
    "offset": 0,
    "limit": 50,
    "total": 1247,
    "has_more": true
  }
}
```

### Example: Paginated Query

```bash
# First page
curl "https://api.example.com/v1/data/calcs/weekly_symbol_volume_by_tier_v1?tier=NMS_TIER_1&week=2025-12-22&limit=50"

# Second page
curl "https://api.example.com/v1/data/calcs/weekly_symbol_volume_by_tier_v1?tier=NMS_TIER_1&week=2025-12-22&limit=50&offset=50"
```

---

## 4. Ordering

### Default Ordering

Each endpoint has a sensible default order:

| Endpoint Type | Default Order |
|---------------|---------------|
| Symbol lists | `volume DESC` (most active first) |
| Week lists | `week_ending DESC` (most recent first) |
| Anomalies | `detected_at DESC, severity ASC` |
| Captures | `captured_at DESC` |

### Custom Ordering (Intermediate+)

Basic tier uses fixed ordering. Intermediate tier adds `order_by` parameter:

```
GET /v1/data/symbols?tier=NMS_TIER_1&week=2025-12-22&order_by=symbol:asc
```

Allowed order fields are documented per endpoint.

---

## 5. Response Envelope

### Standard Data Response

All data-plane responses follow this envelope:

```json
{
  "calc_name": "weekly_symbol_volume_by_tier_v1",
  "calc_version": "v1",
  "calc_deprecated": false,
  "query_time": "2026-01-04T15:30:00Z",
  
  "capture": {
    "capture_id": "finra.otc_transparency:NMS_TIER_1:2025-12-22:20251223",
    "captured_at": "2025-12-23T10:00:00Z",
    "is_latest": true,
    "source": "FINRA OTC Transparency"
  },
  
  "readiness": {
    "is_ready": true,
    "ready_for": "production",
    "blocking_issues": []
  },
  
  "rows": [
    {"symbol": "AAPL", "volume": 12500000, "avg_price": 178.50},
    {"symbol": "MSFT", "volume": 8900000, "avg_price": 375.20}
  ],
  
  "pagination": {
    "offset": 0,
    "limit": 50,
    "total": 1247,
    "has_more": true
  }
}
```

### Envelope Fields

| Section | Field | Type | Description |
|---------|-------|------|-------------|
| **Calc metadata** | `calc_name` | string | Full calc name with version suffix |
| | `calc_version` | string | Extracted version (e.g., "v1") |
| | `calc_deprecated` | boolean | If true, migrate to newer version |
| | `deprecation_message` | string? | Migration guidance (if deprecated) |
| **Query metadata** | `query_time` | ISO timestamp | When this query was processed |
| **Capture metadata** | `capture.capture_id` | string | Unique capture identifier |
| | `capture.captured_at` | ISO timestamp | When data was captured |
| | `capture.is_latest` | boolean | Whether this is the most recent capture |
| | `capture.source` | string? | Data source description |
| **Readiness** | `readiness.is_ready` | boolean | Master readiness flag |
| | `readiness.ready_for` | string? | Use case this is ready for |
| | `readiness.blocking_issues` | string[]? | List of blocking issues (if any) |
| **Data** | `rows` | array | The query results |
| **Pagination** | `pagination.offset` | int | Current offset |
| | `pagination.limit` | int | Page size |
| | `pagination.total` | int | Total matching rows |
| | `pagination.has_more` | boolean | Whether more pages exist |

### Simplified Responses (Basic Tier)

Basic tier may omit some metadata fields for simplicity:

```json
{
  "tier": "NMS_TIER_1",
  "week": "2025-12-22",
  "symbols": [
    {"symbol": "AAPL", "volume": 12500000, "avg_price": 178.50}
  ],
  "count": 1247
}
```

The full envelope is available in Intermediate+ tiers.

---

## 6. Error Model

### Error Response Format

All errors follow this structure:

```json
{
  "error": {
    "code": "DOMAIN_NOT_FOUND",
    "message": "Domain 'invalid.domain' does not exist",
    "details": {
      "domain": "invalid.domain",
      "available_domains": ["finra.otc_transparency"]
    }
  }
}
```

### Standard Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `DOMAIN_NOT_FOUND` | 404 | Requested domain doesn't exist |
| `CALC_NOT_FOUND` | 404 | Requested calc doesn't exist |
| `CAPTURE_NOT_FOUND` | 404 | Requested capture_id doesn't exist |
| `INVALID_TIER` | 400 | Invalid tier parameter value |
| `INVALID_DATE` | 400 | Invalid date format (expected YYYY-MM-DD) |
| `INVALID_SYMBOL` | 400 | Symbol format invalid |
| `MISSING_REQUIRED` | 400 | Required parameter missing |
| `DATA_NOT_READY` | 409 | Data exists but not marked ready |
| `DEPENDENCY_MISSING` | 409 | Calc depends on data that doesn't exist |
| `CALC_DEPRECATED` | 410 | Calc version is deprecated and removed |
| `RATE_LIMITED` | 429 | Too many requests (Intermediate+) |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

### Error Handling Best Practices

```typescript
// Client-side error handling
async function queryCalc(calcName: string, params: QueryParams) {
  const response = await fetch(`/v1/data/calcs/${calcName}?${params}`);
  
  if (!response.ok) {
    const { error } = await response.json();
    
    switch (error.code) {
      case 'DATA_NOT_READY':
        // Show "data processing in progress" message
        return { status: 'pending', message: error.message };
      case 'CALC_DEPRECATED':
        // Log warning, try newer version
        console.warn(`Calc ${calcName} deprecated: ${error.message}`);
        return queryCalc(error.details.replacement_calc, params);
      default:
        throw new ApiError(error.code, error.message);
    }
  }
  
  return response.json();
}
```

---

## 7. Concrete Examples

### Example 1: Query Weekly Symbol Volume

**Request:**
```bash
curl -X GET "http://localhost:8000/v1/data/symbols?tier=NMS_TIER_1&week=2025-12-22&top=5" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
{
  "tier": "NMS_TIER_1",
  "week": "2025-12-22",
  "symbols": [
    {"symbol": "AAPL", "volume": 125000000, "avg_price": 178.50},
    {"symbol": "MSFT", "volume": 89000000, "avg_price": 375.20},
    {"symbol": "NVDA", "volume": 76000000, "avg_price": 495.80},
    {"symbol": "AMZN", "volume": 54000000, "avg_price": 153.25},
    {"symbol": "GOOGL", "volume": 48000000, "avg_price": 140.60}
  ],
  "count": 5
}
```

### Example 2: Query Available Weeks

**Request:**
```bash
curl -X GET "http://localhost:8000/v1/data/weeks?tier=NMS_TIER_1&limit=3" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
{
  "tier": "NMS_TIER_1",
  "weeks": [
    {"week_ending": "2025-12-29", "symbol_count": 8547},
    {"week_ending": "2025-12-22", "symbol_count": 8432},
    {"week_ending": "2025-12-15", "symbol_count": 8389}
  ],
  "count": 3
}
```

### Example 3: Query with Invalid Tier

**Request:**
```bash
curl -X GET "http://localhost:8000/v1/data/symbols?tier=INVALID&week=2025-12-22" \
  -H "Accept: application/json"
```

**Response (400 Bad Request):**
```json
{
  "error": {
    "code": "INVALID_TIER",
    "message": "Unknown tier 'INVALID'. Valid values: NMS_TIER_1, NMS_TIER_2, OTC",
    "details": {
      "parameter": "tier",
      "provided": "INVALID",
      "valid_values": ["NMS_TIER_1", "NMS_TIER_2", "OTC"]
    }
  }
}
```

### Example 4: Query Readiness (Proposed)

**Request:**
```bash
curl -X GET "http://localhost:8000/v1/data/readiness?domain=finra.otc_transparency&week=2025-12-22" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
{
  "domain": "finra.otc_transparency",
  "partition_key": "2025-12-22",
  "readiness": {
    "is_ready": true,
    "ready_for": "production",
    "raw_complete": true,
    "normalized_complete": true,
    "calc_complete": true,
    "no_critical_anomalies": true,
    "checked_at": "2025-12-23T10:30:00Z"
  }
}
```

### Example 5: Query Anomalies (Proposed)

**Request:**
```bash
curl -X GET "http://localhost:8000/v1/data/anomalies?domain=finra.otc_transparency&week=2025-12-22&severity=CRITICAL,ERROR" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
{
  "domain": "finra.otc_transparency",
  "partition_key": "2025-12-22",
  "anomalies": [
    {
      "id": 47,
      "anomaly_type": "MISSING_VENUE",
      "severity": "ERROR",
      "category": "NORMALIZATION",
      "message": "Unknown venue code 'XXXX' for 3 records",
      "details": {
        "venue_code": "XXXX",
        "record_count": 3,
        "sample_symbols": ["XYZ", "ABC"]
      },
      "detected_at": "2025-12-23T10:15:00Z",
      "resolved_at": null
    }
  ],
  "count": 1
}
```

---

## 8. Design Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pagination style | Offset-based | Simplicity, debugging, small datasets |
| Version in URL | Explicit (`venue_share_v1`) | Reproducibility, no implicit upgrades |
| Date format | ISO 8601 (`YYYY-MM-DD`) | Unambiguous, sortable, standard |
| Timestamp format | ISO 8601 with Z suffix | UTC, no timezone confusion |
| Error envelope | Single `error` object | Consistent parsing, extensible |
| Capture as metadata | Envelope field, not URL | Cleaner URLs, optional parameter |
| Readiness in response | Optional section | Allows callers to ignore if not needed |
