# SQL Schema Reference

This document covers the new database tables added for operational tracking.

---

## Overview

Four new schema files were added:
- `02_workflow_history.sql` - Workflow execution tracking
- `03_scheduler.sql` - Cron-based scheduling
- `04_alerting.sql` - Alert channels and delivery
- `05_sources.sql` - Source registry and fetch history

These build on top of the existing `00_core.sql` and `01_domains.sql`.

---

## Schema Files Location

```
packages/spine-core/src/spine/core/schema/
├── 00_core.sql              # Core executions, captures (existing)
├── 01_domains.sql           # Domain tables (existing)
├── 02_workflow_history.sql  # NEW: Workflow runs/steps
├── 03_scheduler.sql         # NEW: Schedules and locks
├── 04_alerting.sql          # NEW: Alert channels/deliveries
└── 05_sources.sql           # NEW: Source registry/fetches
```

---

## 02_workflow_history.sql

### `core_workflow_runs`

Tracks each workflow execution.

| Column | Type | Description |
|--------|------|-------------|
| `run_id` | TEXT PK | ULID or deterministic ID |
| `workflow_name` | TEXT | e.g., "finra.weekly_ingest" |
| `workflow_version` | INTEGER | Schema version |
| `domain` | TEXT | e.g., "finra.otc_transparency" |
| `partition_key` | TEXT (JSON) | {"week_ending": "2025-01-10", "tier": "..."} |
| `status` | TEXT | PENDING → RUNNING → COMPLETED/FAILED/CANCELLED |
| `started_at` | TEXT | ISO timestamp |
| `completed_at` | TEXT | ISO timestamp |
| `duration_ms` | INTEGER | Computed on completion |
| `params` | TEXT (JSON) | Input parameters |
| `outputs` | TEXT (JSON) | Final outputs |
| `error` | TEXT | Error message if failed |
| `error_category` | TEXT | Error classification |
| `error_retryable` | INTEGER | 1=retryable, 0=permanent |
| `total_steps` | INTEGER | Total step count |
| `completed_steps` | INTEGER | Steps completed |
| `failed_steps` | INTEGER | Steps failed |
| `skipped_steps` | INTEGER | Steps skipped |
| `triggered_by` | TEXT | manual, schedule, api, parent_workflow |
| `parent_run_id` | TEXT | FK to parent (nested workflows) |
| `schedule_id` | TEXT | FK to core_schedules |
| `created_at` | TEXT | Creation timestamp |
| `created_by` | TEXT | User/system that triggered |
| `capture_id` | TEXT | Links outputs to this run |

**Indexes**:
- `idx_workflow_runs_status` - Filter by status
- `idx_workflow_runs_name` - Filter by workflow name
- `idx_workflow_runs_domain` - Filter by domain
- `idx_workflow_runs_started` - Order by start time
- `idx_workflow_runs_failed` - Find failed runs

### `core_workflow_steps`

Tracks each step within a workflow run.

| Column | Type | Description |
|--------|------|-------------|
| `step_id` | TEXT PK | ULID |
| `run_id` | TEXT FK | Links to core_workflow_runs |
| `step_name` | TEXT | e.g., "fetch_data", "validate" |
| `step_type` | TEXT | pipeline, lambda, choice, etc. |
| `step_order` | INTEGER | Execution order (0-based) |
| `status` | TEXT | PENDING → RUNNING → COMPLETED/FAILED/SKIPPED |
| `started_at` | TEXT | ISO timestamp |
| `completed_at` | TEXT | ISO timestamp |
| `duration_ms` | INTEGER | Step duration |
| `params` | TEXT (JSON) | Input parameters |
| `outputs` | TEXT (JSON) | Step outputs |
| `error` | TEXT | Error message |
| `error_category` | TEXT | Error classification |
| `row_count` | INTEGER | Rows processed |
| `metrics` | TEXT (JSON) | Additional metrics |
| `attempt` | INTEGER | Current attempt (for retries) |
| `max_attempts` | INTEGER | Max retry attempts |
| `execution_id` | TEXT FK | Links to core_executions (pipeline steps) |

**Unique Constraint**: `(run_id, step_name, attempt)`

### `core_workflow_events`

Immutable event log for state transitions.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `run_id` | TEXT FK | Links to core_workflow_runs |
| `step_id` | TEXT FK | Links to core_workflow_steps (NULL for run events) |
| `event_type` | TEXT | started, completed, failed, retrying, etc. |
| `timestamp` | TEXT | Event timestamp |
| `payload` | TEXT (JSON) | Event-specific data |
| `idempotency_key` | TEXT UNIQUE | Prevents duplicate events |

---

## 03_scheduler.sql

### `core_schedules`

Stores schedule definitions.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | ULID |
| `name` | TEXT UNIQUE | e.g., "finra.weekly_refresh" |
| `target_type` | TEXT | pipeline, workflow |
| `target_name` | TEXT | Name of target to execute |
| `params` | TEXT (JSON) | Default parameters |
| `schedule_type` | TEXT | cron, interval, date |
| `cron_expression` | TEXT | e.g., "0 6 * * 1-5" |
| `interval_seconds` | INTEGER | For interval schedules |
| `run_at` | TEXT | For one-time schedules |
| `timezone` | TEXT | Default: UTC |
| `enabled` | INTEGER | 1=enabled, 0=disabled |
| `max_instances` | INTEGER | Prevent overlapping runs |
| `misfire_grace_seconds` | INTEGER | Allow late execution |
| `last_run_at` | TEXT | Last execution time |
| `next_run_at` | TEXT | Next scheduled time |
| `last_run_status` | TEXT | COMPLETED, FAILED |
| `created_at` | TEXT | Creation timestamp |
| `updated_at` | TEXT | Last update timestamp |
| `created_by` | TEXT | Creator |
| `version` | INTEGER | For versioning |

### `core_schedule_runs`

Tracks scheduled execution attempts.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | ULID |
| `schedule_id` | TEXT FK | Links to core_schedules |
| `schedule_name` | TEXT | Denormalized for queries |
| `scheduled_at` | TEXT | When it was supposed to run |
| `started_at` | TEXT | When it actually started |
| `completed_at` | TEXT | When it finished |
| `status` | TEXT | PENDING, RUNNING, COMPLETED, FAILED, SKIPPED, MISSED |
| `run_id` | TEXT FK | Links to core_workflow_runs |
| `execution_id` | TEXT FK | Links to core_executions |
| `error` | TEXT | Error message |
| `skip_reason` | TEXT | Why skipped |

### `core_schedule_locks`

Distributed lock support (Advanced tier).

| Column | Type | Description |
|--------|------|-------------|
| `schedule_id` | TEXT PK | FK to core_schedules |
| `locked_by` | TEXT | Instance ID |
| `locked_at` | TEXT | Lock acquisition time |
| `expires_at` | TEXT | Auto-release time |

---

## 04_alerting.sql

### `core_alert_channels`

Alert channel configurations.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | ULID |
| `name` | TEXT UNIQUE | e.g., "slack-prod" |
| `channel_type` | TEXT | slack, email, webhook, etc. |
| `config_json` | TEXT | Type-specific configuration |
| `min_severity` | TEXT | INFO, WARNING, ERROR, CRITICAL |
| `domains` | TEXT (JSON) | Domain filter patterns |
| `enabled` | INTEGER | 1=enabled, 0=disabled |
| `throttle_minutes` | INTEGER | Min interval between alerts |
| `last_success_at` | TEXT | Last successful delivery |
| `last_failure_at` | TEXT | Last failed delivery |
| `consecutive_failures` | INTEGER | Failure count |
| `created_at` | TEXT | Creation timestamp |
| `updated_at` | TEXT | Last update |
| `created_by` | TEXT | Creator |

**Config JSON Examples**:

```json
// Slack
{
  "webhook_url": "https://hooks.slack.com/...",
  "channel": "#alerts"
}

// Email
{
  "smtp_host": "smtp.company.com",
  "recipients": ["ops@company.com"],
  "from": "spine@company.com"
}
```

### `core_alerts`

Alert delivery log.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | ULID |
| `severity` | TEXT | INFO, WARNING, ERROR, CRITICAL |
| `title` | TEXT | Short summary |
| `message` | TEXT | Detailed message |
| `source` | TEXT | Pipeline/workflow that triggered |
| `domain` | TEXT | Domain context |
| `execution_id` | TEXT FK | Related execution |
| `run_id` | TEXT FK | Related workflow run |
| `metadata_json` | TEXT | Additional context |
| `error_category` | TEXT | Error classification |
| `created_at` | TEXT | Creation timestamp |
| `dedup_key` | TEXT | For throttling |
| `capture_id` | TEXT | Related capture |

### `core_alert_deliveries`

Delivery status per channel.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | ULID |
| `alert_id` | TEXT FK | Links to core_alerts |
| `channel_id` | TEXT FK | Links to core_alert_channels |
| `channel_name` | TEXT | Denormalized |
| `status` | TEXT | PENDING, SENT, FAILED, THROTTLED |
| `attempted_at` | TEXT | Attempt timestamp |
| `delivered_at` | TEXT | Delivery confirmation |
| `response_json` | TEXT | Channel response |
| `error` | TEXT | Error message |
| `attempt` | INTEGER | Attempt number |
| `next_retry_at` | TEXT | Retry time |

**Unique Constraint**: `(alert_id, channel_id, attempt)`

### `core_alert_throttle`

Deduplication tracking.

| Column | Type | Description |
|--------|------|-------------|
| `dedup_key` | TEXT PK | Hash of source+title+severity |
| `last_sent_at` | TEXT | When last sent |
| `send_count` | INTEGER | Times sent in window |
| `expires_at` | TEXT | When entry can be removed |

---

## 05_sources.sql

### `core_sources`

Source registry.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | ULID |
| `name` | TEXT UNIQUE | e.g., "finra.otc.weekly" |
| `source_type` | TEXT | file, http, database, s3, sftp |
| `config_json` | TEXT | Type-specific config |
| `domain` | TEXT | Domain association |
| `enabled` | INTEGER | 1=enabled, 0=disabled |
| `created_at` | TEXT | Creation timestamp |
| `updated_at` | TEXT | Last update |
| `created_by` | TEXT | Creator |

**Config JSON Examples**:

```json
// File
{
  "path": "data/*.psv",
  "format": "psv"
}

// HTTP
{
  "url": "https://api.example.com",
  "auth": {"type": "bearer", "token_ref": "..."}
}

// Database
{
  "connection": "prod-postgres",
  "query": "SELECT * FROM trades WHERE date > :date"
}
```

### `core_source_fetches`

Fetch operation history.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | ULID |
| `source_id` | TEXT FK | Links to core_sources |
| `source_name` | TEXT | Source identifier |
| `source_type` | TEXT | file, http, database |
| `source_locator` | TEXT | Path, URL, or query |
| `status` | TEXT | SUCCESS, FAILED, NOT_FOUND, UNCHANGED |
| `record_count` | INTEGER | Rows fetched |
| `byte_count` | INTEGER | Size in bytes |
| `content_hash` | TEXT | For change detection |
| `etag` | TEXT | HTTP ETag |
| `last_modified` | TEXT | File mtime or HTTP header |
| `started_at` | TEXT | Fetch start time |
| `completed_at` | TEXT | Fetch end time |
| `duration_ms` | INTEGER | Fetch duration |
| `error` | TEXT | Error message |
| `error_category` | TEXT | Error classification |
| `retry_count` | INTEGER | Retry attempts |
| `execution_id` | TEXT FK | Related execution |
| `run_id` | TEXT FK | Related workflow run |
| `capture_id` | TEXT | Resulting capture |
| `metadata_json` | TEXT | Additional metadata |

### `core_source_cache`

Content cache (Advanced tier).

| Column | Type | Description |
|--------|------|-------------|
| `cache_key` | TEXT PK | Hash of source+params |
| `source_id` | TEXT FK | Links to core_sources |
| `source_type` | TEXT | Source type |
| `source_locator` | TEXT | Original path/URL |
| `content_hash` | TEXT | Hash of cached content |
| `content_size` | INTEGER | Size in bytes |
| `content_path` | TEXT | Local file path |
| `content_blob` | BLOB | Inline content (small) |
| `fetched_at` | TEXT | When fetched |
| `expires_at` | TEXT | Cache expiration |
| `etag` | TEXT | For revalidation |
| `last_modified` | TEXT | For revalidation |
| `metadata_json` | TEXT | Source metadata |
| `last_accessed_at` | TEXT | For LRU eviction |

### `core_database_connections`

Database connection registry.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | ULID |
| `name` | TEXT UNIQUE | e.g., "prod-postgres" |
| `dialect` | TEXT | sqlite, postgresql, db2 |
| `host` | TEXT | Hostname |
| `port` | INTEGER | Port |
| `database` | TEXT | Database name/path |
| `username` | TEXT | Username |
| `password_ref` | TEXT | Reference to secret store |
| `pool_size` | INTEGER | Default: 5 |
| `max_overflow` | INTEGER | Default: 10 |
| `pool_timeout` | INTEGER | Default: 30 |
| `enabled` | INTEGER | 1=enabled |
| `last_connected_at` | TEXT | Last connection |
| `last_error` | TEXT | Last error |
| `last_error_at` | TEXT | Error timestamp |
| `created_at` | TEXT | Creation timestamp |
| `updated_at` | TEXT | Last update |
| `created_by` | TEXT | Creator |

---

## Index Strategy

All tables follow consistent indexing patterns:

```sql
-- Status filtering (most common)
CREATE INDEX idx_*_status ON table(status);

-- Time-based queries
CREATE INDEX idx_*_created ON table(created_at);
CREATE INDEX idx_*_started ON table(started_at);

-- Foreign key lookups
CREATE INDEX idx_*_run ON child_table(run_id);
CREATE INDEX idx_*_source ON child_table(source_id);

-- Partial indexes for efficiency
CREATE INDEX idx_*_failed ON table(status, created_at) WHERE status = 'FAILED';
CREATE INDEX idx_*_retry ON table(next_retry_at) WHERE status = 'FAILED';
```

---

## Migration Notes

### Running Migrations

```bash
# SQLite (Basic tier)
sqlite3 data.db < schema/02_workflow_history.sql
sqlite3 data.db < schema/03_scheduler.sql
sqlite3 data.db < schema/04_alerting.sql
sqlite3 data.db < schema/05_sources.sql

# PostgreSQL (Intermediate tier)
# Syntax adjustments needed for:
# - TEXT → VARCHAR/TEXT
# - datetime('now') → NOW()
# - AUTOINCREMENT → SERIAL
```

### Tier Requirements

| Table | Basic | Intermediate | Advanced |
|-------|-------|--------------|----------|
| core_workflow_runs | ❌ | ✅ | ✅ |
| core_workflow_steps | ❌ | ✅ | ✅ |
| core_workflow_events | ❌ | ✅ | ✅ |
| core_schedules | ❌ | ✅ | ✅ |
| core_schedule_runs | ❌ | ✅ | ✅ |
| core_schedule_locks | ❌ | ❌ | ✅ |
| core_alert_channels | ❌ | ✅ | ✅ |
| core_alerts | ❌ | ✅ | ✅ |
| core_alert_deliveries | ❌ | ✅ | ✅ |
| core_sources | ❌ | ✅ | ✅ |
| core_source_fetches | ❌ | ✅ | ✅ |
| core_source_cache | ❌ | ❌ | ✅ |
| core_database_connections | ❌ | ✅ | ✅ |
