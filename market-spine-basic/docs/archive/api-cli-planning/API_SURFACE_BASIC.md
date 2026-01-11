# API Surface — Basic Tier

> **Purpose**: Define the initial API endpoints for Basic tier, with request/response examples and mapping to CLI commands.

---

## Design Principles

1. **RESTful** — Resources are nouns; actions map to HTTP verbs
2. **Versioned** — All endpoints under `/v1/` from day one
3. **Consistent** — Same semantics as CLI commands
4. **Self-documenting** — OpenAPI spec generated from code
5. **Minimal** — Only expose what's needed; expand later

---

## Endpoint Overview

| Endpoint | Method | CLI Equivalent | Description |
|----------|--------|----------------|-------------|
| `/v1/pipelines` | GET | `spine pipelines list` | List available pipelines |
| `/v1/pipelines/{name}` | GET | `spine pipelines describe {name}` | Describe a pipeline |
| `/v1/pipelines/{name}/resolve` | POST | `spine run run {name} --explain-source` | Resolve ingest source |
| `/v1/executions` | POST | `spine run run {name} ...` | Run a pipeline |
| `/v1/executions/{id}` | GET | *(new)* | Get execution status |
| `/v1/query/weeks` | GET | `spine query weeks` | Query available weeks |
| `/v1/query/symbols` | GET | `spine query symbols` | Query top symbols |
| `/v1/verify/tables/{name}` | GET | `spine verify table {name}` | Verify table |
| `/v1/verify/data` | GET | `spine verify data` | Verify data integrity |
| `/v1/health` | GET | `spine doctor doctor` | Health check |

---

## Detailed Endpoint Specifications

### Pipeline Discovery

#### List Pipelines

```
GET /v1/pipelines
GET /v1/pipelines?prefix=finra.otc
```

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `prefix` | string | No | Filter pipelines by name prefix |

**Response: 200 OK**
```json
{
  "pipelines": [
    {
      "name": "finra.otc_transparency.ingest_week",
      "description": "Ingest FINRA OTC transparency file for one week"
    },
    {
      "name": "finra.otc_transparency.normalize_week",
      "description": "Normalize raw FINRA OTC transparency data for one week"
    },
    {
      "name": "finra.otc_transparency.aggregate_week",
      "description": "Compute FINRA OTC transparency aggregates for one week"
    }
  ],
  "count": 3,
  "total": 5
}
```

**CLI Mapping:**
```bash
# Equivalent CLI command
spine pipelines list --prefix finra.otc
```

---

#### Describe Pipeline

```
GET /v1/pipelines/finra.otc_transparency.ingest_week
```

**Path Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `name` | string | Full pipeline name |

**Response: 200 OK**
```json
{
  "name": "finra.otc_transparency.ingest_week",
  "description": "Ingest FINRA OTC transparency file for one week",
  "parameters": {
    "required": [
      {
        "name": "file_path",
        "type": "path",
        "description": "Path to the FINRA OTC transparency PSV file"
      }
    ],
    "optional": [
      {
        "name": "tier",
        "type": "string",
        "description": "Market tier (auto-detected from filename if not provided)",
        "valid_values": ["NMS_TIER_1", "NMS_TIER_2", "OTC"],
        "aliases": ["tier1", "tier2", "t1", "t2", "otc"]
      },
      {
        "name": "week_ending",
        "type": "date",
        "description": "Week ending date in ISO format (auto-detected if not provided)",
        "format": "YYYY-MM-DD"
      },
      {
        "name": "force",
        "type": "boolean",
        "description": "Re-ingest even if already ingested",
        "default": false
      }
    ]
  },
  "ingest_info": {
    "is_ingest_pipeline": true,
    "source_resolution": {
      "explicit_mode": "Provide file_path parameter directly",
      "derived_mode": "Derived from tier + week_ending",
      "pattern": "data/finra/finra_otc_weekly_{tier}_{date}.csv"
    }
  },
  "examples": [
    "spine run finra.otc_transparency.ingest_week -p file_path=data/week.psv",
    "spine run finra.otc_transparency.ingest_week -p file_path=data/t1.psv -p tier=NMS_TIER_1"
  ]
}
```

**Response: 404 Not Found**
```json
{
  "error": {
    "code": "PIPELINE_NOT_FOUND",
    "message": "Pipeline 'unknown.pipeline' not found",
    "available_pipelines": ["finra.otc_transparency.ingest_week", "..."]
  }
}
```

**CLI Mapping:**
```bash
# Equivalent CLI command
spine pipelines describe finra.otc_transparency.ingest_week
```

---

#### Resolve Ingest Source

```
POST /v1/pipelines/finra.otc_transparency.ingest_week/resolve
```

**Request Body:**
```json
{
  "params": {
    "tier": "OTC",
    "week_ending": "2025-12-19"
  }
}
```

**Response: 200 OK**
```json
{
  "resolution": {
    "mode": "derived",
    "file_path": "data/finra/finra_otc_weekly_otc_2025-12-19.csv",
    "derivation": {
      "pattern": "data/finra/finra_otc_weekly_{tier}_{date}.csv",
      "substitutions": {
        "tier": "otc",
        "date": "2025-12-19"
      }
    }
  },
  "validation": {
    "valid": true,
    "normalized_params": {
      "tier": "OTC",
      "week_ending": "2025-12-19"
    }
  }
}
```

**Response: 200 OK (with explicit file)**
```json
{
  "resolution": {
    "mode": "explicit",
    "file_path": "/path/to/custom/file.psv",
    "derivation": null
  },
  "validation": {
    "valid": true,
    "normalized_params": {
      "file_path": "/path/to/custom/file.psv",
      "tier": "OTC"
    }
  }
}
```

**CLI Mapping:**
```bash
# Equivalent CLI command
spine run run finra.otc_transparency.ingest_week --explain-source --dry-run tier=OTC week_ending=2025-12-19
```

---

### Pipeline Execution

#### Run Pipeline

```
POST /v1/executions
```

**Request Body:**
```json
{
  "pipeline": "finra.otc_transparency.normalize_week",
  "params": {
    "week_ending": "2025-12-19",
    "tier": "NMS_TIER_1"
  },
  "options": {
    "dry_run": false,
    "lane": "normal"
  }
}
```

**Response: 200 OK (Synchronous in Basic)**
```json
{
  "execution_id": "exec_7f3a9b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "pipeline": "finra.otc_transparency.normalize_week",
  "status": "completed",
  "started_at": "2025-12-19T10:30:00Z",
  "completed_at": "2025-12-19T10:30:05Z",
  "duration_ms": 5234,
  "params": {
    "week_ending": "2025-12-19",
    "tier": "NMS_TIER_1"
  },
  "metrics": {
    "rows_processed": 15420,
    "rows_normalized": 15418,
    "rows_rejected": 2
  }
}
```

**Response: 200 OK (Dry Run)**
```json
{
  "execution_id": null,
  "pipeline": "finra.otc_transparency.normalize_week",
  "status": "dry_run",
  "dry_run": true,
  "params": {
    "week_ending": "2025-12-19",
    "tier": "NMS_TIER_1"
  },
  "validation": {
    "valid": true,
    "message": "Parameters valid. Would execute with these settings."
  }
}
```

**Response: 400 Bad Request (Invalid Parameters)**
```json
{
  "error": {
    "code": "INVALID_PARAMS",
    "message": "Parameter validation failed",
    "details": {
      "missing": ["file_path"],
      "invalid": {
        "tier": "Invalid tier: UNKNOWN. Valid values: NMS_TIER_1, NMS_TIER_2, OTC"
      }
    }
  }
}
```

**Response: 500 Internal Server Error (Pipeline Failed)**
```json
{
  "execution_id": "exec_7f3a9b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "pipeline": "finra.otc_transparency.normalize_week",
  "status": "failed",
  "started_at": "2025-12-19T10:30:00Z",
  "completed_at": "2025-12-19T10:30:02Z",
  "duration_ms": 2341,
  "error": {
    "code": "PIPELINE_FAILED",
    "message": "No raw data found for week 2025-12-19, tier NMS_TIER_1"
  }
}
```

**CLI Mapping:**
```bash
# Equivalent CLI commands
spine run run finra.otc_transparency.normalize_week week_ending=2025-12-19 tier=NMS_TIER_1

# Dry run
spine run run finra.otc_transparency.normalize_week --dry-run week_ending=2025-12-19 tier=NMS_TIER_1
```

---

#### Get Execution Status

```
GET /v1/executions/exec_7f3a9b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c
```

**Response: 200 OK**
```json
{
  "execution_id": "exec_7f3a9b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "pipeline": "finra.otc_transparency.normalize_week",
  "status": "completed",
  "lane": "normal",
  "trigger_source": "api",
  "created_at": "2025-12-19T10:29:59Z",
  "started_at": "2025-12-19T10:30:00Z",
  "completed_at": "2025-12-19T10:30:05Z",
  "duration_ms": 5234,
  "params": {
    "week_ending": "2025-12-19",
    "tier": "NMS_TIER_1"
  },
  "metrics": {
    "rows_processed": 15420,
    "rows_normalized": 15418,
    "rows_rejected": 2
  }
}
```

**Response: 404 Not Found**
```json
{
  "error": {
    "code": "EXECUTION_NOT_FOUND",
    "message": "Execution 'exec_unknown' not found"
  }
}
```

**Note:** This is a **new capability** not directly available in CLI. Useful for tracking executions programmatically.

---

### Data Queries

#### Query Available Weeks

```
GET /v1/query/weeks?tier=NMS_TIER_1&limit=10
```

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `tier` | string | Yes | Market tier (supports aliases) |
| `limit` | integer | No | Max results (default: 10) |

**Response: 200 OK**
```json
{
  "tier": "NMS_TIER_1",
  "weeks": [
    {
      "week_ending": "2025-12-19",
      "symbol_count": 3421
    },
    {
      "week_ending": "2025-12-12",
      "symbol_count": 3398
    },
    {
      "week_ending": "2025-12-05",
      "symbol_count": 3415
    }
  ],
  "count": 3,
  "limit": 10
}
```

**Response: 400 Bad Request (Invalid Tier)**
```json
{
  "error": {
    "code": "INVALID_TIER",
    "message": "Invalid tier: UNKNOWN",
    "valid_values": ["NMS_TIER_1", "NMS_TIER_2", "OTC"]
  }
}
```

**CLI Mapping:**
```bash
# Equivalent CLI command
spine query weeks --tier NMS_TIER_1 --limit 10
```

---

#### Query Top Symbols

```
GET /v1/query/symbols?tier=NMS_TIER_1&week=2025-12-19&top=10
```

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `tier` | string | Yes | Market tier |
| `week` | string | Yes | Week ending date (YYYY-MM-DD) |
| `top` | integer | No | Number of symbols (default: 10) |

**Response: 200 OK**
```json
{
  "tier": "NMS_TIER_1",
  "week_ending": "2025-12-19",
  "symbols": [
    {
      "symbol": "AAPL",
      "total_shares": 125000000,
      "total_trades": 892345,
      "avg_trade_size": 140
    },
    {
      "symbol": "TSLA",
      "total_shares": 98000000,
      "total_trades": 723456,
      "avg_trade_size": 135
    }
  ],
  "count": 10,
  "top": 10
}
```

**CLI Mapping:**
```bash
# Equivalent CLI command
spine query symbols --tier NMS_TIER_1 --week 2025-12-19 --top 10
```

---

### Verification & Health

#### Verify Table

```
GET /v1/verify/tables/finra_otc_transparency_raw
```

**Response: 200 OK**
```json
{
  "table": "finra_otc_transparency_raw",
  "exists": true,
  "row_count": 156789,
  "status": "ok"
}
```

**Response: 200 OK (Table Missing)**
```json
{
  "table": "finra_otc_transparency_aggregated",
  "exists": false,
  "row_count": null,
  "status": "missing"
}
```

**CLI Mapping:**
```bash
# Equivalent CLI command
spine verify table finra_otc_transparency_raw
```

---

#### Health Check

```
GET /v1/health
```

**Response: 200 OK (Healthy)**
```json
{
  "status": "healthy",
  "checks": [
    {
      "name": "database",
      "status": "ok",
      "message": "SQLite connection successful"
    },
    {
      "name": "table:finra_otc_transparency_raw",
      "status": "ok",
      "message": "Table exists with 156789 rows"
    },
    {
      "name": "table:finra_otc_transparency_normalized",
      "status": "ok",
      "message": "Table exists with 145678 rows"
    },
    {
      "name": "table:finra_otc_transparency_aggregated",
      "status": "warning",
      "message": "Table exists but is empty"
    }
  ],
  "timestamp": "2025-12-19T10:45:00Z"
}
```

**Response: 503 Service Unavailable (Unhealthy)**
```json
{
  "status": "unhealthy",
  "checks": [
    {
      "name": "database",
      "status": "error",
      "message": "Unable to connect to database"
    }
  ],
  "timestamp": "2025-12-19T10:45:00Z"
}
```

**CLI Mapping:**
```bash
# Equivalent CLI command
spine doctor doctor
```

---

## Error Response Format

All errors follow a consistent structure:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": { ... }  // Optional additional context
  }
}
```

**Standard Error Codes:**
| Code | HTTP Status | Description |
|------|-------------|-------------|
| `PIPELINE_NOT_FOUND` | 404 | Pipeline name not in registry |
| `EXECUTION_NOT_FOUND` | 404 | Execution ID not found |
| `INVALID_PARAMS` | 400 | Parameter validation failed |
| `INVALID_TIER` | 400 | Tier value not recognized |
| `MISSING_REQUIRED_PARAM` | 400 | Required parameter missing |
| `PIPELINE_FAILED` | 500 | Pipeline execution failed |
| `DATABASE_ERROR` | 500 | Database operation failed |

---

## API vs CLI Feature Comparison

| Feature | CLI | API | Notes |
|---------|-----|-----|-------|
| Pipeline list | ✅ | ✅ | Same filtering |
| Pipeline describe | ✅ | ✅ | API returns JSON schema |
| Pipeline run | ✅ | ✅ | Sync in Basic |
| Execution tracking | ⚠️ In-memory | ✅ By ID | API enables external tracking |
| Dry run | ✅ | ✅ | Same semantics |
| Ingest resolution | ✅ | ✅ | API returns structured |
| Query weeks | ✅ | ✅ | Same query |
| Query symbols | ✅ | ✅ | Same query |
| Table verify | ✅ | ✅ | Same checks |
| Health check | ✅ | ✅ | API returns JSON |
| Interactive mode | ✅ | ❌ | CLI-only feature |
| Progress bars | ✅ | ❌ | CLI-only feature |
| Log streaming | ✅ (terminal) | ❌ | Future: SSE/WebSocket |

---

## Framework Choice Discussion

### Option A: FastAPI (Recommended)

**Pros:**
- Automatic OpenAPI generation
- Pydantic integration (already used in models)
- Async-ready (for Intermediate tier)
- Modern, well-documented
- TestClient for easy testing

**Cons:**
- Slightly larger dependency
- Async can be confusing if not needed

### Option B: Flask

**Pros:**
- Simpler, minimal
- Well-known

**Cons:**
- Manual OpenAPI generation
- No async support (requires different stack later)
- More boilerplate for validation

### Option C: Starlette

**Pros:**
- Minimal, FastAPI's foundation
- Async-native

**Cons:**
- Less automatic schema generation
- More manual work

### Recommendation

**FastAPI for Basic tier.** The automatic OpenAPI generation and Pydantic integration provide immediate value. The async capability isn't needed now but doesn't hurt, and it makes Intermediate tier transition seamless.

```python
# market_spine/api/main.py
from fastapi import FastAPI

app = FastAPI(
    title="Market Spine API",
    version="1.0.0",
    description="Analytics Pipeline System",
)

# Auto-generated OpenAPI at /docs
```

---

## CLI Entry Point

Add a new CLI command to start the API server:

```bash
# Start API server
spine api

# With options
spine api --port 8000 --host 0.0.0.0 --reload
```

```python
# market_spine/cli/commands/api.py

@app.command("api")
def run_api_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Start the API server."""
    import uvicorn
    uvicorn.run(
        "market_spine.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )
```
