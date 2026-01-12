# API Routes Reference

This document covers the REST API endpoints added for workflow, schedule, alert, and source management.

---

## Overview

Four new route modules were added to `market-spine-intermediate`:

| Module | Prefix | Description |
|--------|--------|-------------|
| `routes/workflows.py` | `/api/v1/workflows` | Workflow execution management |
| `routes/schedules.py` | `/api/v1/schedules` | Schedule CRUD and control |
| `routes/alerts.py` | `/api/v1/alerts` | Alert channels and delivery |
| `routes/sources.py` | `/api/v1/sources` | Source registry and fetches |

All routes follow [API_DESIGN_GUARDRAILS.md](../API_DESIGN_GUARDRAILS.md) and [PAGINATION_FILTERING_STANDARDS.md](../PAGINATION_FILTERING_STANDARDS.md).

---

## Common Patterns

### Pagination

All list endpoints use offset/limit pagination:

```
GET /api/v1/workflows/runs?offset=0&limit=20
```

Response includes pagination metadata:

```json
{
  "data": [...],
  "pagination": {
    "offset": 0,
    "limit": 20,
    "total": 150,
    "has_more": true
  }
}
```

### Standard Responses

**Success (mutation)**:
```json
{
  "id": "01HXYZ...",
  "status": "created",
  "message": "Schedule created successfully"
}
```

**Error**:
```json
{
  "detail": "Schedule not found: abc123"
}
```

---

## Workflow Routes (`/api/v1/workflows`)

### List Workflow Runs

```
GET /runs
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| `status` | string | Filter by status (PENDING, RUNNING, etc.) |
| `workflow_name` | string | Filter by workflow name |
| `domain` | string | Filter by domain |
| `since` | datetime | Only runs started after this time |
| `until` | datetime | Only runs started before this time |
| `offset` | int | Pagination offset (default: 0) |
| `limit` | int | Page size (default: 20, max: 100) |

**Response**: `WorkflowRunListResponse`

### Get Workflow Run Detail

```
GET /runs/{run_id}
```

**Response**: `WorkflowRunDetail` with steps

### Trigger Workflow

```
POST /trigger/{workflow_name}
```

**Body**:
```json
{
  "params": {"week_ending": "2026-01-10"}
}
```

**Response**: `WorkflowTriggerResponse`

### Cancel Workflow Run

```
POST /runs/{run_id}/cancel
```

**Response**: `ActionResponse`

### Retry Failed Workflow

```
POST /runs/{run_id}/retry
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| `from_step` | string | Optional step to retry from |

**Response**: `WorkflowTriggerResponse`

### List Workflow Definitions

```
GET /definitions
```

**Response**: List of registered workflows

### Get Workflow Definition

```
GET /definitions/{workflow_name}
```

**Response**: `WorkflowDefinition`

---

## Schedule Routes (`/api/v1/schedules`)

### List Schedules

```
GET /
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Filter by enabled status |
| `target_type` | string | Filter by target type |
| `target_name` | string | Filter by target name |
| `offset` | int | Pagination offset |
| `limit` | int | Page size |

**Response**: `ScheduleListResponse`

### Get Schedule

```
GET /{schedule_id}
```

**Response**: `ScheduleResponse`

### Create Schedule

```
POST /
```

**Body**: `ScheduleCreate`
```json
{
  "name": "finra.weekly",
  "target_type": "WORKFLOW",
  "target_name": "finra.weekly_refresh",
  "cron_expression": "0 6 * * 1",
  "timezone": "America/New_York",
  "target_params": {"tier": "NMS_TIER_1"}
}
```

**Response**: `ActionResponse`

### Update Schedule

```
PATCH /{schedule_id}
```

**Body**: `ScheduleUpdate` (partial)

**Response**: `ScheduleResponse`

### Delete Schedule

```
DELETE /{schedule_id}
```

**Response**: `ActionResponse`

### Enable Schedule

```
POST /{schedule_id}/enable
```

**Response**: `ActionResponse`

### Disable Schedule

```
POST /{schedule_id}/disable
```

**Response**: `ActionResponse`

### Run Now

```
POST /{schedule_id}/run-now
```

Triggers the schedule immediately (ignores cron).

**Response**: `WorkflowTriggerResponse`

### Get Schedule Runs

```
GET /{schedule_id}/runs
```

**Query Parameters**: Standard pagination

**Response**: `ScheduleRunListResponse`

### Preview Next Runs

```
GET /preview-next
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| `count` | int | Number of runs to preview (default: 5) |

**Response**: List of `NextRunPreview`

---

## Alert Routes (`/api/v1/alerts`)

### Channels

#### List Channels

```
GET /channels
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| `channel_type` | string | Filter by type (slack, email, etc.) |
| `enabled` | bool | Filter by enabled status |
| `offset` | int | Pagination offset |
| `limit` | int | Page size |

**Response**: `AlertChannelListResponse`

#### Get Channel

```
GET /channels/{channel_id}
```

**Response**: `AlertChannelResponse`

#### Create Channel

```
POST /channels
```

**Body**: `AlertChannelCreate`
```json
{
  "name": "ops-slack",
  "channel_type": "slack",
  "config": {
    "webhook_url": "https://hooks.slack.com/...",
    "channel": "#alerts"
  },
  "min_severity": "ERROR",
  "domains": ["finra.*"]
}
```

**Response**: `ActionResponse`

#### Update Channel

```
PATCH /channels/{channel_id}
```

**Body**: `AlertChannelUpdate`

**Response**: `AlertChannelResponse`

#### Delete Channel

```
DELETE /channels/{channel_id}
```

**Response**: `ActionResponse`

#### Test Channel

```
POST /channels/{channel_id}/test
```

Sends a test alert to verify configuration.

**Response**: `ChannelTestResponse`

### Alerts

#### List Alerts

```
GET /
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| `severity` | string | Filter by severity |
| `source` | string | Filter by source |
| `domain` | string | Filter by domain |
| `since` | datetime | Only alerts after this time |
| `offset` | int | Pagination offset |
| `limit` | int | Page size |

**Response**: `AlertListResponse`

#### Get Alert Detail

```
GET /{alert_id}
```

**Response**: `AlertDetail` with deliveries

#### Send Manual Alert

```
POST /
```

**Body**: `AlertCreate`
```json
{
  "severity": "ERROR",
  "title": "Manual Alert Test",
  "message": "Testing the alerting system",
  "source": "manual"
}
```

**Response**: `ActionResponse`

#### Get Alert Statistics

```
GET /stats
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| `period` | string | hour, day, week, month |

**Response**: `AlertStats`

---

## Source Routes (`/api/v1/sources`)

### Sources

#### List Sources

```
GET /
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| `source_type` | string | Filter by type (file, http, etc.) |
| `domain` | string | Filter by domain |
| `enabled` | bool | Filter by enabled status |
| `offset` | int | Pagination offset |
| `limit` | int | Page size |

**Response**: `SourceListResponse`

#### Get Source

```
GET /{source_id}
```

**Response**: `SourceDetail`

#### Create Source

```
POST /
```

**Body**: `SourceCreate`
```json
{
  "name": "finra.otc.weekly",
  "source_type": "file",
  "domain": "finra.otc_transparency",
  "config": {
    "path": "/data/finra/*.psv",
    "format": "psv"
  }
}
```

**Response**: `ActionResponse`

#### Update Source

```
PATCH /{source_id}
```

**Body**: `SourceUpdate`

**Response**: `SourceDetail`

#### Delete Source

```
DELETE /{source_id}
```

**Response**: `ActionResponse`

### Fetches

#### Trigger Fetch

```
POST /{source_id}/fetch
```

Triggers an immediate fetch from the source.

**Response**: `FetchTriggerResponse`

#### Get Fetch History

```
GET /{source_id}/fetches
```

**Query Parameters**: Standard pagination

**Response**: `FetchListResponse`

#### Get Fetch Detail

```
GET /fetches/{fetch_id}
```

**Response**: `FetchDetail`

### Cache

#### List Cache Entries

```
GET /cache
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| `source_id` | string | Filter by source |
| `offset` | int | Pagination offset |
| `limit` | int | Page size |

**Response**: `CacheListResponse`

#### Get Cache Statistics

```
GET /cache/stats
```

**Response**: `CacheStats`

#### Clear Cache

```
DELETE /cache
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| `source_id` | string | Clear only for this source |
| `expired_only` | bool | Only clear expired entries |

**Response**: `ActionResponse`

### Database Connections

#### List Connections

```
GET /connections
```

**Response**: `DatabaseConnectionListResponse`

#### Get Connection

```
GET /connections/{connection_id}
```

**Response**: `DatabaseConnectionResponse`

#### Create Connection

```
POST /connections
```

**Body**: `DatabaseConnectionCreate`
```json
{
  "name": "prod-postgres",
  "db_type": "postgresql",
  "host": "db.company.com",
  "port": 5432,
  "database": "spine",
  "username": "spine_user",
  "password_ref": "vault:postgres/spine"
}
```

**Response**: `ActionResponse`

#### Test Connection

```
POST /connections/{connection_id}/test
```

Tests database connectivity.

**Response**:
```json
{
  "success": true,
  "message": "Connected successfully",
  "latency_ms": 15
}
```

#### Delete Connection

```
DELETE /connections/{connection_id}
```

**Response**: `ActionResponse`

---

## Authentication

All endpoints require authentication (handled at router level):

```python
router = APIRouter(
    prefix="/api/v1/workflows",
    tags=["workflows"],
    dependencies=[Depends(verify_api_key)],  # Or JWT
)
```

---

## Error Codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad request (validation error) |
| 401 | Unauthorized |
| 404 | Resource not found |
| 409 | Conflict (duplicate name) |
| 422 | Unprocessable entity |
| 500 | Internal server error |
