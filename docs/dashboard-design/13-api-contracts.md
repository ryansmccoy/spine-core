# API Contract Mapping

> Part of: [Dashboard Design](00-index.md)

## Overview

This document maps each dashboard page to the backend APIs required, identifying existing endpoints and gaps.

---

## 1. Global Overview Page

### Required APIs

| Data | Endpoint | Status | Tier |
|------|----------|--------|------|
| Health status | `GET /health` | ✅ Exists | Basic |
| Capabilities | `GET /v1/capabilities` | ✅ Exists | Basic |
| Pipeline count | `GET /v1/pipelines` | ✅ Exists | Basic |
| Latest week per tier | `GET /v1/data/weeks?tier=X&limit=1` | ✅ Exists | Basic |
| Failed executions (24h) | `GET /v1/executions?status=failed&since=24h` | ❌ Missing | Intermediate |
| Running executions | `GET /v1/executions?status=running` | ❌ Missing | Intermediate |
| Scheduled runs | `GET /v1/schedules/upcoming` | ❌ Missing | Intermediate |
| Overdue runs | `GET /v1/schedules/overdue` | ❌ Missing | Intermediate |

### Response Shapes Needed

**Health Response** (exists):
```json
{
  "status": "ok",
  "timestamp": "2025-01-04T10:30:00Z",
  "checks": [
    { "name": "database", "status": "ok", "latency_ms": 3 }
  ]
}
```

**Executions Response** (needed for Intermediate):
```json
{
  "executions": [
    {
      "execution_id": "abc-123",
      "pipeline": "finra.otc.ingest_week",
      "status": "failed",
      "started_at": "2025-01-04T08:10:00Z",
      "completed_at": "2025-01-04T08:10:12Z",
      "error_summary": "HTTP 503 from FINRA"
    }
  ],
  "count": 1
}
```

---

## 2. Pipelines Page

### Required APIs

| Data | Endpoint | Status | Tier |
|------|----------|--------|------|
| List pipelines | `GET /v1/pipelines` | ✅ Exists | Basic |
| Pipeline detail | `GET /v1/pipelines/{name}` | ✅ Exists | Basic |
| Run pipeline | `POST /v1/pipelines/{name}/run` | ✅ Exists | Basic |
| Pipeline last run | `GET /v1/pipelines/{name}/last-run` | ❌ Missing | Basic |
| Pipeline history | `GET /v1/executions?pipeline={name}` | ❌ Missing | Intermediate |
| Pipeline schedule | `GET /v1/schedules/{pipeline}` | ❌ Missing | Intermediate |
| Update schedule | `PUT /v1/schedules/{pipeline}` | ❌ Missing | Intermediate |

### Response Shapes Needed

**Pipeline Last Run** (proposed for Basic):
```json
{
  "pipeline": "finra.otc.ingest_week",
  "last_execution": {
    "execution_id": "abc-123",
    "status": "completed",
    "started_at": "2025-01-04T08:15:00Z",
    "duration_seconds": 45
  }
}
```

**Pipeline Schedule** (needed for Intermediate):
```json
{
  "pipeline": "finra.otc.ingest_week",
  "schedule": {
    "cron": "0 8 * * MON",
    "timezone": "America/New_York",
    "enabled": true,
    "next_run": "2025-01-06T08:00:00Z",
    "last_run": "2024-12-30T08:00:00Z"
  }
}
```

---

## 3. Executions Page

### Required APIs

| Data | Endpoint | Status | Tier |
|------|----------|--------|------|
| List executions | `GET /v1/executions` | ❌ Missing | Intermediate |
| Execution detail | `GET /v1/executions/{id}` | ❌ Missing | Intermediate |
| Execution logs | `GET /v1/executions/{id}/logs` | ❌ Missing | Intermediate |
| Retry execution | `POST /v1/executions/{id}/retry` | ❌ Missing | Intermediate |
| Cancel execution | `POST /v1/executions/{id}/cancel` | ❌ Missing | Intermediate |

### Response Shapes Needed

**Execution List**:
```json
{
  "executions": [
    {
      "execution_id": "abc-123",
      "pipeline": "finra.otc.ingest_week",
      "status": "completed",
      "trigger": "scheduled",
      "started_at": "2025-01-04T08:15:00Z",
      "completed_at": "2025-01-04T08:15:45Z",
      "duration_seconds": 45,
      "rows_processed": 15847,
      "capture_id": "cap_20250104_0815"
    }
  ],
  "count": 100,
  "has_more": true,
  "next_cursor": "cursor_xyz"
}
```

**Execution Detail**:
```json
{
  "execution_id": "abc-123",
  "pipeline": "finra.otc.ingest_week",
  "status": "failed",
  "trigger": "manual",
  "triggered_by": "user@example.com",
  "started_at": "2025-01-04T08:10:00Z",
  "completed_at": "2025-01-04T08:10:12Z",
  "duration_seconds": 12,
  "params": {
    "week_ending": "2025-12-22",
    "tier": "OTC",
    "dry_run": false
  },
  "capture_id": "cap_20250104_0810",
  "error": {
    "type": "HTTPError",
    "message": "HTTP 503: Service Temporarily Unavailable",
    "traceback": "...",
    "classification": "transient"
  },
  "output": null,
  "logs_url": "/v1/executions/abc-123/logs"
}
```

**Execution Logs**:
```json
{
  "execution_id": "abc-123",
  "logs": [
    {
      "timestamp": "2025-01-04T08:10:15.123Z",
      "level": "INFO",
      "message": "Starting pipeline execution"
    },
    {
      "timestamp": "2025-01-04T08:10:27.456Z",
      "level": "ERROR",
      "message": "HTTP 503 from api.finra.org"
    }
  ],
  "truncated": false
}
```

---

## 4. Data Readiness Page

### Required APIs

| Data | Endpoint | Status | Tier |
|------|----------|--------|------|
| Weeks by tier | `GET /v1/data/weeks?tier=X` | ✅ Exists | Basic |
| Readiness status | `GET /v1/data/readiness?tier=X` | ❌ Missing | Intermediate |
| Certify data | `POST /v1/data/readiness/certify` | ❌ Missing | Intermediate |
| Block data | `POST /v1/data/readiness/block` | ❌ Missing | Intermediate |
| Dependencies | `GET /v1/data/dependencies?dataset=X` | ❌ Missing | Advanced |

### Response Shapes Needed

**Readiness Status** (needed for Intermediate):
```json
{
  "tier": "OTC",
  "weeks": [
    {
      "week_ending": "2025-12-22",
      "status": "certified",
      "symbol_count": 2847,
      "certified_at": "2025-01-03T14:00:00Z",
      "certified_by": "system",
      "anomaly_count": { "critical": 0, "high": 0, "medium": 1, "low": 2 }
    },
    {
      "week_ending": "2025-12-15",
      "status": "preliminary",
      "symbol_count": 2812,
      "certified_at": null,
      "anomaly_count": { "critical": 0, "high": 1, "medium": 0, "low": 0 }
    }
  ]
}
```

---

## 5. Quality Page

### Required APIs

| Data | Endpoint | Status | Tier |
|------|----------|--------|------|
| Anomaly list | `GET /v1/quality/anomalies` | ❌ Missing | Intermediate |
| Anomaly detail | `GET /v1/quality/anomalies/{id}` | ❌ Missing | Intermediate |
| Acknowledge | `POST /v1/quality/anomalies/{id}/ack` | ❌ Missing | Intermediate |
| Detection rules | `GET /v1/quality/rules` | ❌ Missing | Intermediate |
| Create rule | `POST /v1/quality/rules` | ❌ Missing | Advanced |

### Response Shapes Needed

**Anomaly List**:
```json
{
  "anomalies": [
    {
      "id": "anomaly-001",
      "type": "missing_data",
      "severity": "critical",
      "tier": "OTC",
      "week": "2025-12-22",
      "description": "15 symbols absent from data",
      "detected_at": "2025-01-04T08:30:00Z",
      "acknowledged": false,
      "affected_symbols": ["ACME", "BETA", "CORP"]
    }
  ],
  "summary": {
    "critical": 2,
    "high": 5,
    "medium": 12,
    "low": 8
  }
}
```

---

## 6. Data Assets Page

### Required APIs

| Data | Endpoint | Status | Tier |
|------|----------|--------|------|
| Weeks by tier | `GET /v1/data/weeks?tier=X` | ✅ Exists | Basic |
| Symbols for week | `GET /v1/data/symbols?tier=X&week=Y` | ✅ Exists | Basic |
| Symbol search | `GET /v1/data/symbols/search?q=X` | ❌ Missing | Basic |
| Symbol history | `GET /v1/data/symbols/{symbol}/history` | ❌ Missing | Basic |
| Storage stats | `GET /v1/ops/storage` | ✅ Exists | Basic |
| Download data | `GET /v1/data/export?tier=X&week=Y` | ❌ Missing | Basic |
| Derived datasets | `GET /v1/data/calcs` | ❌ Missing | Intermediate |

### Response Shapes Needed

**Symbol Search**:
```json
{
  "query": "AAPL",
  "results": [
    {
      "symbol": "AAPL",
      "name": "Apple Inc.",
      "availability": {
        "OTC": { "weeks": 52, "earliest": "2024-01-07", "latest": "2025-12-22" },
        "NMS_TIER_1": { "weeks": 48, "earliest": "2024-02-04", "latest": "2025-12-22" }
      },
      "latest_volume": 45678901
    }
  ]
}
```

**Symbol History**:
```json
{
  "symbol": "AAPL",
  "tier": "OTC",
  "history": [
    {
      "week_ending": "2025-12-22",
      "volume": 45678901,
      "trade_count": 12345,
      "avg_price": 189.45,
      "rank": 1
    },
    {
      "week_ending": "2025-12-15",
      "volume": 40789012,
      "trade_count": 11234,
      "avg_price": 175.32,
      "rank": 1
    }
  ],
  "count": 52
}
```

---

## 7. Settings Page

### Required APIs

| Data | Endpoint | Status | Tier |
|------|----------|--------|------|
| Capabilities | `GET /v1/capabilities` | ✅ Exists | Basic |
| Storage stats | `GET /v1/ops/storage` | ✅ Exists | Basic |
| Health detailed | `GET /health/detailed` | ✅ Exists | Basic |
| Configuration | `GET /v1/config` | ❌ Missing | Basic |
| Update config | `PUT /v1/config` | ❌ Missing | Intermediate |
| Notifications | `GET /v1/notifications/config` | ❌ Missing | Advanced |
| Webhooks | `GET /v1/webhooks` | ❌ Missing | Advanced |

---

## API Gap Summary

### Basic Tier - Currently Missing

| Endpoint | Priority | Purpose |
|----------|----------|---------|
| `GET /v1/pipelines/{name}/last-run` | High | Show last run status in pipeline list |
| `GET /v1/data/symbols/search` | Medium | Global symbol search |
| `GET /v1/data/symbols/{symbol}/history` | High | Symbol history view |
| `GET /v1/data/export` | Low | CSV/JSON download |
| `GET /v1/config` | Low | Settings display |

### Intermediate Tier - All Missing

| Endpoint | Priority | Purpose |
|----------|----------|---------|
| `GET /v1/executions` | Critical | Execution history |
| `GET /v1/executions/{id}` | Critical | Execution detail |
| `GET /v1/executions/{id}/logs` | Critical | Execution logs |
| `POST /v1/executions/{id}/retry` | High | Retry failed |
| `POST /v1/executions/{id}/cancel` | High | Cancel running |
| `GET /v1/schedules/*` | High | Scheduling |
| `GET /v1/data/readiness` | High | Certification status |
| `GET /v1/quality/anomalies` | High | Quality checks |
| `GET /v1/data/calcs` | Medium | Derived analytics |

### Advanced Tier - All Missing

| Endpoint | Priority | Purpose |
|----------|----------|---------|
| `GET /v1/data/dependencies` | Medium | Lineage |
| `GET /v1/notifications/*` | Medium | Alerting |
| `GET /v1/webhooks/*` | Medium | Webhooks |
| `GET /v1/users/*` | Low | Multi-tenant |
| `GET /v1/audit/*` | Low | Audit trail |

---

## Implementation Priority

### Phase 1: Basic Tier Complete

1. `GET /v1/pipelines/{name}/last-run`
2. `GET /v1/data/symbols/{symbol}/history`
3. `GET /v1/data/symbols/search`

### Phase 2: Intermediate Foundation

1. `GET/POST /v1/executions/*`
2. `GET/PUT /v1/schedules/*`
3. `GET /v1/data/readiness`

### Phase 3: Quality & Analytics

1. `GET /v1/quality/anomalies`
2. `GET /v1/data/calcs`
3. `POST /v1/data/readiness/certify`

### Phase 4: Advanced Features

1. Alerting endpoints
2. Lineage endpoints
3. Audit endpoints
