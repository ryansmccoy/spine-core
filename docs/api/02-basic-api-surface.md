# Basic Tier API Surface

> Last Updated: 2026-01-05  
> Version: 1.1  
> Status: **AUTHORITATIVE**

This document defines the complete API surface for the Basic tier, including existing endpoints and proposed additions for data access.

---

## 1. Current Basic API (Implemented)

### Route Overview

| Prefix | Purpose |
|--------|---------|
| `/health` | Health checks (no version prefix) |
| `/v1/capabilities` | Feature discovery |
| `/v1/pipelines` | Pipeline operations |
| `/v1/data` | Data queries |
| `/v1/ops` | Operations and monitoring |

### Health Endpoints

#### GET /health

Basic liveness check.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-04T15:30:00Z"
}
```

#### GET /health/detailed

Comprehensive health with component checks.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-04T15:30:00Z",
  "components": {
    "database": {"status": "healthy", "latency_ms": 2},
    "connection_pool": {"status": "healthy", "active": 1, "idle": 4}
  }
}
```

### Discovery Endpoints

#### GET /v1/capabilities

Returns tier feature flags for client adaptation.

**Response (200 OK):**
```json
{
  "api_version": "v1",
  "tier": "basic",
  "version": "0.5.0",
  "sync_execution": true,
  "async_execution": false,
  "execution_history": false,
  "authentication": false,
  "scheduling": false,
  "rate_limiting": false,
  "webhook_notifications": false
}
```

### Pipeline Endpoints (Control Plane)

#### GET /v1/pipelines

List available pipelines.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prefix` | string | No | Filter by name prefix |

**Response (200 OK):**
```json
{
  "pipelines": [
    {"name": "finra.otc_transparency.ingest_week", "description": "Ingest FINRA OTC weekly data"},
    {"name": "finra.otc_transparency.normalize_week", "description": "Normalize OTC data"},
    {"name": "finra.otc_transparency.calculate_metrics", "description": "Calculate weekly metrics"}
  ],
  "count": 3
}
```

#### GET /v1/pipelines/{pipeline_name}

Get pipeline details including parameter schema.

**Response (200 OK):**
```json
{
  "name": "finra.otc_transparency.ingest_week",
  "description": "Ingest FINRA OTC weekly transparency data from PSV file",
  "required_params": [
    {"name": "week_ending", "type": "date", "description": "Week ending date (YYYY-MM-DD)"},
    {"name": "tier", "type": "string", "description": "Tier: NMS_TIER_1, NMS_TIER_2, OTC"},
    {"name": "file", "type": "path", "description": "Path to PSV data file"}
  ],
  "optional_params": [
    {"name": "batch_size", "type": "int", "description": "Rows per batch", "default": 1000}
  ],
  "is_ingest": true
}
```

**Error Response (404 Not Found):**
```json
{
  "error": {
    "code": "PIPELINE_NOT_FOUND",
    "message": "Pipeline 'invalid.pipeline' not found"
  }
}
```

#### POST /v1/pipelines/{pipeline_name}/run

Execute a pipeline synchronously.

**Request Body:**
```json
{
  "params": {
    "week_ending": "2025-12-22",
    "tier": "NMS_TIER_1",
    "file": "data/fixtures/otc/week_2025-12-22.psv"
  },
  "dry_run": false,
  "lane": "default"
}
```

**Response (200 OK):**
```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "pipeline": "finra.otc_transparency.ingest_week",
  "status": "completed",
  "rows_processed": 15847,
  "duration_seconds": 2.34,
  "poll_url": null
}
```

**Error Response (400 Bad Request):**
```json
{
  "error": {
    "code": "INVALID_PARAMS",
    "message": "Missing required parameter: week_ending"
  }
}
```

### Data Endpoints (Data Plane - Current)

#### GET /v1/data/weeks

List available weeks of processed data.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tier` | string | Yes | Tier: NMS_TIER_1, NMS_TIER_2, OTC |
| `limit` | int | No | Max weeks (default: 10, max: 100) |

**Response (200 OK):**
```json
{
  "tier": "NMS_TIER_1",
  "weeks": [
    {"week_ending": "2025-12-29", "symbol_count": 8547},
    {"week_ending": "2025-12-22", "symbol_count": 8432}
  ],
  "count": 2
}
```

#### GET /v1/data/symbols

List top symbols by volume for a week.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tier` | string | Yes | Tier code |
| `week` | string | Yes | Week ending (YYYY-MM-DD) |
| `top` | int | No | Number of symbols (default: 10, max: 100) |

**Response (200 OK):**
```json
{
  "tier": "NMS_TIER_1",
  "week": "2025-12-22",
  "symbols": [
    {"symbol": "AAPL", "volume": 125000000, "avg_price": 178.50},
    {"symbol": "MSFT", "volume": 89000000, "avg_price": 375.20}
  ],
  "count": 2
}
```

#### GET /v1/data/symbols/{symbol}/history

Query historical trading data for a specific symbol.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Trading symbol (e.g., AAPL) |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tier` | string | Yes | Tier: NMS_TIER_1, NMS_TIER_2, OTC |
| `weeks` | int | No | Number of weeks (default: 12, max: 52) |

**Response (200 OK):**
```json
{
  "symbol": "AAPL",
  "tier": "NMS_TIER_1",
  "history": [
    {"week_ending": "2025-12-08", "total_shares": 125000000, "total_trades": 45230, "average_price": null},
    {"week_ending": "2025-12-15", "total_shares": 132000000, "total_trades": 48100, "average_price": null},
    {"week_ending": "2025-12-22", "total_shares": 118000000, "total_trades": 42500, "average_price": null}
  ],
  "count": 3
}
```

**Error Response (400 Bad Request):**
```json
{
  "error": {
    "code": "INVALID_TIER",
    "message": "Invalid tier: 'INVALID'. Must be one of: NMS_TIER_1, NMS_TIER_2, OTC"
  }
}
```

### Operations Endpoints

#### GET /v1/ops/storage

Get current storage statistics.

**Response (200 OK):**
```json
{
  "database_path": "/app/data/market_spine.db",
  "database_size_bytes": 15728640,
  "tables": [
    {"name": "finra_otc_transparency_normalized", "row_count": 125847, "size_bytes": null},
    {"name": "data_readiness", "row_count": 12, "size_bytes": null}
  ],
  "total_rows": 125859
}
```

#### GET /v1/ops/captures

List all data captures in the system.

**Response (200 OK):**
```json
{
  "captures": [
    {
      "capture_id": "finra.otc_transparency:NMS_TIER_1:2025-12-22:20251223",
      "captured_at": "2025-12-23T10:00:00Z",
      "tier": "NMS_TIER_1",
      "week_ending": "2025-12-22",
      "row_count": 8547
    },
    {
      "capture_id": "finra.otc_transparency:OTC:2025-12-22:20251223",
      "captured_at": "2025-12-23T10:05:00Z",
      "tier": "OTC",
      "week_ending": "2025-12-22",
      "row_count": 15234
    }
  ],
  "count": 2
}
```

---

## 2. Proposed Basic API Additions

### Design Decision: Tables vs Calcs

**Question**: Should Basic expose raw "tables" or only "calcs"?

**Decision**: Expose **calcs only** in the data plane.

**Rationale**:
1. **Consistency**: Calcs have versioned, documented schemas
2. **Abstraction**: Hides internal table structure from consumers
3. **Evolution**: Can change table layout without breaking API
4. **Quality**: Calcs are computed after normalization and quality checks
5. **Simplicity**: Fewer endpoints to document and maintain

Raw table access (if ever needed) would be a separate admin/debug endpoint, not part of the standard data plane.

### Proposed Endpoints

#### GET /v1/data/domains

List available data domains.

**Response (200 OK):**
```json
{
  "domains": [
    {
      "name": "finra.otc_transparency",
      "description": "FINRA OTC weekly transparency data",
      "partitions": ["tier", "week_ending"],
      "calcs_available": 3
    }
  ],
  "count": 1
}
```

#### GET /v1/data/calcs

List available calculations.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | string | No | Filter by domain |
| `include_deprecated` | bool | No | Include deprecated calcs (default: false) |

**Response (200 OK):**
```json
{
  "calcs": [
    {
      "name": "weekly_symbol_volume_by_tier_v1",
      "version": "v1",
      "domain": "finra.otc_transparency",
      "description": "Total volume per symbol/tier/week",
      "deprecated": false,
      "output_columns": ["symbol", "tier", "week_ending", "total_volume", "trade_count", "avg_price"]
    },
    {
      "name": "venue_share_v1",
      "version": "v1",
      "domain": "finra.otc_transparency",
      "description": "Venue share of volume for each symbol",
      "deprecated": false,
      "output_columns": ["symbol", "venue", "week_ending", "volume", "share_pct"]
    }
  ],
  "count": 2
}
```

#### GET /v1/data/calcs/{calc_name}

Query a specific calculation.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tier` | string | Depends | Required for FINRA calcs |
| `week` | string | Depends | Required for weekly calcs |
| `symbol` | string | No | Filter by symbol |
| `venue` | string | No | Filter by venue |
| `limit` | int | No | Max rows (default: 50, max: 1000) |
| `offset` | int | No | Pagination offset |

**Response (200 OK):**
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
  "rows": [
    {"symbol": "AAPL", "tier": "NMS_TIER_1", "week_ending": "2025-12-22", "total_volume": 125000000, "trade_count": 45230, "avg_price": 178.50},
    {"symbol": "MSFT", "tier": "NMS_TIER_1", "week_ending": "2025-12-22", "total_volume": 89000000, "trade_count": 32100, "avg_price": 375.20}
  ],
  "pagination": {
    "offset": 0,
    "limit": 50,
    "total": 8432,
    "has_more": true
  }
}
```

#### GET /v1/data/readiness

Query data readiness status.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | string | Yes | Domain name |
| `week` | string | No | Specific week (or returns all) |

**Response (200 OK):**
```json
{
  "domain": "finra.otc_transparency",
  "partitions": [
    {
      "partition_key": "NMS_TIER_1:2025-12-22",
      "is_ready": true,
      "ready_for": "production",
      "raw_complete": true,
      "normalized_complete": true,
      "calc_complete": true,
      "no_critical_anomalies": true,
      "checked_at": "2025-12-23T10:30:00Z"
    },
    {
      "partition_key": "NMS_TIER_1:2025-12-29",
      "is_ready": false,
      "ready_for": null,
      "raw_complete": true,
      "normalized_complete": true,
      "calc_complete": false,
      "no_critical_anomalies": true,
      "checked_at": "2025-12-30T09:15:00Z",
      "notes": "Awaiting metric calculation"
    }
  ],
  "count": 2
}
```

#### GET /v1/data/anomalies

Query data anomalies.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | string | Yes | Domain name |
| `week` | string | No | Specific week |
| `severity` | string | No | Filter: CRITICAL, ERROR, WARN, INFO (comma-separated) |
| `resolved` | bool | No | Filter by resolution status |
| `limit` | int | No | Max results (default: 50) |

**Response (200 OK):**
```json
{
  "domain": "finra.otc_transparency",
  "anomalies": [
    {
      "id": 47,
      "partition_key": "NMS_TIER_1:2025-12-22",
      "anomaly_type": "UNKNOWN_VENUE",
      "severity": "WARN",
      "category": "NORMALIZATION",
      "message": "Unknown venue code 'XXXX' mapped to OTHER",
      "details": {
        "venue_code": "XXXX",
        "record_count": 3
      },
      "detected_at": "2025-12-23T10:15:00Z",
      "resolved_at": null
    }
  ],
  "count": 1
}
```

---

## 3. Complete Route Map (After Additions)

### Control Plane (`/v1/ops/*` — future rename consideration)

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| GET | `/health` | Liveness check | ✅ Implemented |
| GET | `/health/detailed` | Component health | ✅ Implemented |
| GET | `/v1/capabilities` | Feature flags | ✅ Implemented |
| GET | `/v1/pipelines` | List pipelines | ✅ Implemented |
| GET | `/v1/pipelines/{name}` | Pipeline details | ✅ Implemented |
| POST | `/v1/pipelines/{name}/run` | Execute pipeline | ✅ Implemented |
| GET | `/v1/ops/storage` | Storage statistics | ✅ Implemented |
| GET | `/v1/ops/captures` | List data captures | ✅ Implemented |

### Data Plane (`/v1/data/*`)

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| GET | `/v1/data/weeks` | List weeks | ✅ Implemented |
| GET | `/v1/data/symbols` | Top symbols | ✅ Implemented |
| GET | `/v1/data/symbols/{symbol}/history` | Symbol history | ✅ Implemented |
| GET | `/v1/data/domains` | List domains | 📋 Proposed |
| GET | `/v1/data/calcs` | List calcs | 📋 Proposed |
| GET | `/v1/data/calcs/{name}` | Query calc | 📋 Proposed |
| GET | `/v1/data/readiness` | Readiness status | 📋 Proposed |
| GET | `/v1/data/anomalies` | Anomaly list | 📋 Proposed |

---

## 4. Implementation Recommendations

### Minimal Changes Approach

To implement the proposed endpoints with minimal disruption:

#### Step 1: Add App Layer Commands

Create query commands in `market_spine/app/commands/`:

```python
# queries.py (extend existing)

@dataclass
class QueryCalcRequest:
    calc_name: str
    filters: dict[str, Any]
    limit: int = 50
    offset: int = 0

@dataclass  
class QueryCalcResponse:
    success: bool
    calc_name: str
    calc_version: str
    capture_id: str | None
    captured_at: datetime | None
    rows: list[dict]
    total: int
    error: ErrorInfo | None = None
```

#### Step 2: Add Calc Registry

Leverage existing registry pattern:

```python
# app/services/calc_registry.py

@dataclass
class CalcDefinition:
    name: str
    version: str
    domain: str
    description: str
    table_name: str  # Maps to actual DB table
    output_columns: list[str]
    required_filters: list[str]
    deprecated: bool = False

class CalcRegistry:
    """Registry of available calculations."""
    
    _calcs: dict[str, CalcDefinition] = {}
    
    @classmethod
    def register(cls, calc: CalcDefinition) -> None:
        cls._calcs[calc.name] = calc
    
    @classmethod
    def get(cls, name: str) -> CalcDefinition | None:
        return cls._calcs.get(name)
    
    @classmethod
    def list_all(cls, domain: str | None = None) -> list[CalcDefinition]:
        calcs = cls._calcs.values()
        if domain:
            calcs = [c for c in calcs if c.domain == domain]
        return list(calcs)
```

#### Step 3: Add API Routes

Create new route module:

```python
# api/routes/v1/data.py

router = APIRouter(prefix="/data", tags=["Data"])

@router.get("/calcs", response_model=ListCalcsResponse)
async def list_calcs(domain: str | None = None):
    # Uses CalcRegistry
    ...

@router.get("/calcs/{calc_name}", response_model=QueryCalcResponse)
async def query_calc(calc_name: str, tier: str, week: str, ...):
    # Uses QueryCalcCommand
    ...
```

#### Step 4: Register FINRA Calcs

During app startup, register built-in calcs:

```python
# domains/finra/otc_transparency/calcs.py

def register_finra_calcs():
    CalcRegistry.register(CalcDefinition(
        name="weekly_symbol_volume_by_tier_v1",
        version="v1",
        domain="finra.otc_transparency",
        description="Total volume per symbol/tier/week",
        table_name="finra_otc_normalized",  # Or a view/query
        output_columns=["symbol", "tier", "week_ending", "total_volume", "trade_count", "avg_price"],
        required_filters=["tier", "week"],
    ))
```

---

## 5. Error Codes (Complete List)

| Code | HTTP | When |
|------|------|------|
| `PIPELINE_NOT_FOUND` | 404 | Pipeline name doesn't exist |
| `DOMAIN_NOT_FOUND` | 404 | Domain doesn't exist |
| `CALC_NOT_FOUND` | 404 | Calc name doesn't exist |
| `CAPTURE_NOT_FOUND` | 404 | Capture ID doesn't exist |
| `INVALID_TIER` | 400 | Tier parameter invalid |
| `INVALID_DATE` | 400 | Date format invalid |
| `INVALID_PARAMS` | 400 | General parameter validation failure |
| `MISSING_REQUIRED` | 400 | Required parameter missing |
| `DATA_NOT_READY` | 409 | Data exists but not ready |
| `CALC_DEPRECATED` | 410 | Calc removed (not just deprecated) |
| `INTERNAL_ERROR` | 500 | Unexpected error |

---

## 6. Compatibility Notes

### Frontend Impact

The frontend (`trading-desktop`) currently uses:
- `/v1/data/weeks` — ✅ No change
- `/v1/data/symbols` — ✅ No change

New endpoints are additive. The frontend can adopt them progressively:
- Use `/v1/data/calcs/weekly_symbol_volume_by_tier_v1` for richer data
- Check `/v1/data/readiness` before displaying data as authoritative
- Display `/v1/data/anomalies` in a data quality dashboard widget

### CLI Parity

New API endpoints should have CLI equivalents:

```bash
# Current
uv run spine query weeks --tier NMS_TIER_1
uv run spine query symbols --tier NMS_TIER_1 --week 2025-12-22

# Proposed additions
uv run spine query domains
uv run spine query calcs --domain finra.otc_transparency
uv run spine query calc weekly_symbol_volume_by_tier_v1 --tier NMS_TIER_1 --week 2025-12-22
uv run spine query readiness --domain finra.otc_transparency
uv run spine query anomalies --domain finra.otc_transparency --severity CRITICAL
```
