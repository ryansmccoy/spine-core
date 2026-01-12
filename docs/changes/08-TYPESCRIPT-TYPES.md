# TypeScript Types Reference

This document covers the TypeScript interface definitions added for frontend integration.

---

## Overview

All new API responses have matching TypeScript interfaces in:

```
trading-desktop/src/api/operationsTypes.ts
```

These follow [FRONTEND_CONTRACT_PRINCIPLES.md](../FRONTEND_CONTRACT_PRINCIPLES.md).

---

## Common Types

### PaginationMeta

```typescript
export interface PaginationMeta {
  offset: number;
  limit: number;
  total: number;
  has_more: boolean;
}
```

### PaginatedResponse

```typescript
export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta;
}
```

### ActionResponse

```typescript
export interface ActionResponse {
  id: string;
  status: string;
  message: string;
}
```

---

## Workflow Types

### Status Enums

```typescript
export type WorkflowRunStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type WorkflowStepStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "SKIPPED";

export type WorkflowTriggerType =
  | "SCHEDULE"
  | "MANUAL"
  | "API"
  | "DEPENDENCY"
  | "RETRY";
```

### WorkflowRunSummary

```typescript
export interface WorkflowRunSummary {
  run_id: string;
  workflow_name: string;
  status: WorkflowRunStatus;
  trigger: WorkflowTriggerType;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  step_count: number;
  completed_step_count: number;
}
```

### WorkflowStepDetail

```typescript
export interface WorkflowStepDetail {
  step_id: string;
  run_id: string;
  step_name: string;
  step_index: number;
  status: WorkflowStepStatus;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  inputs: Record<string, unknown> | null;
  outputs: Record<string, unknown> | null;
  error: string | null;
  error_category: string | null;
  retry_count: number;
}
```

### WorkflowRunDetail

```typescript
export interface WorkflowRunDetail extends WorkflowRunSummary {
  domain: string | null;
  input_params: Record<string, unknown> | null;
  execution_id: string | null;
  error: string | null;
  error_category: string | null;
  rows_processed: number | null;
  steps: WorkflowStepDetail[];
  triggered_by: string | null;
  parent_run_id: string | null;
  capture_id: string | null;
}
```

### WorkflowTriggerResponse

```typescript
export interface WorkflowTriggerResponse {
  run_id: string;
  workflow_name: string;
  status: "PENDING" | "STARTED";
  message: string;
}
```

### WorkflowDefinition

```typescript
export interface WorkflowDefinition {
  name: string;
  domain: string | null;
  description: string;
  step_count: number;
  parameters: Array<{
    name: string;
    type: string;
    required: boolean;
    default?: unknown;
  }>;
}
```

---

## Schedule Types

### ScheduleTargetType

```typescript
export type ScheduleTargetType = "PIPELINE" | "WORKFLOW" | "COMMAND";
```

### ScheduleCreate

```typescript
export interface ScheduleCreate {
  name: string;
  description?: string;
  target_type: ScheduleTargetType;
  target_name: string;
  target_params?: Record<string, unknown>;
  cron_expression?: string;
  interval_seconds?: number;
  timezone?: string;
  enabled?: boolean;
  tags?: string[];
}
```

### ScheduleUpdate

```typescript
export interface ScheduleUpdate {
  description?: string;
  cron_expression?: string;
  interval_seconds?: number;
  target_params?: Record<string, unknown>;
  timezone?: string;
  enabled?: boolean;
  tags?: string[];
}
```

### ScheduleResponse

```typescript
export interface ScheduleResponse {
  id: string;
  name: string;
  description: string | null;
  target_type: ScheduleTargetType;
  target_name: string;
  target_params: Record<string, unknown> | null;
  cron_expression: string | null;
  interval_seconds: number | null;
  timezone: string;
  enabled: boolean;
  tags: string[] | null;
  
  // Timing
  last_run_at: string | null;
  next_run_at: string | null;
  
  // Stats
  run_count: number;
  success_count: number;
  failure_count: number;
  consecutive_failures: number;
  
  // Audit
  created_at: string;
  updated_at: string;
  created_by: string | null;
}
```

### ScheduleRunSummary

```typescript
export interface ScheduleRunSummary {
  id: string;
  schedule_id: string;
  status: "COMPLETED" | "FAILED" | "SKIPPED" | "RUNNING";
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  run_id: string | null;
  error: string | null;
}
```

---

## Alert Types

### Severity and Status Enums

```typescript
export type AlertSeverity = "INFO" | "WARNING" | "ERROR" | "CRITICAL";
export type AlertChannelType = "slack" | "email" | "servicenow" | "webhook";
export type AlertDeliveryStatus = "PENDING" | "SENT" | "FAILED" | "THROTTLED";
```

### Channel Configurations

```typescript
export interface ChannelConfigSlack {
  webhook_url: string;
  channel?: string;
  username?: string;
}

export interface ChannelConfigEmail {
  smtp_host: string;
  smtp_port: number;
  smtp_user?: string;
  from_address: string;
  recipients: string[];
  use_tls?: boolean;
}
```

### AlertChannelCreate

```typescript
export interface AlertChannelCreate {
  name: string;
  channel_type: AlertChannelType;
  config: ChannelConfigSlack | ChannelConfigEmail | Record<string, unknown>;
  min_severity?: AlertSeverity;
  domains?: string[];
  enabled?: boolean;
  throttle_minutes?: number;
}
```

### AlertChannelResponse

```typescript
export interface AlertChannelResponse {
  id: string;
  name: string;
  channel_type: AlertChannelType;
  config: Record<string, unknown>; // Sensitive fields redacted
  min_severity: AlertSeverity;
  domains: string[] | null;
  enabled: boolean;
  throttle_minutes: number;
  
  // Health
  last_success_at: string | null;
  last_failure_at: string | null;
  consecutive_failures: number;
  
  // Audit
  created_at: string;
  updated_at: string;
  created_by: string | null;
}
```

### AlertSummary

```typescript
export interface AlertSummary {
  id: string;
  severity: AlertSeverity;
  title: string;
  source: string;
  domain: string | null;
  created_at: string;
  delivery_count: number;
  success_count: number;
  failed_count: number;
}
```

### AlertDetail

```typescript
export interface AlertDetail extends AlertSummary {
  message: string;
  execution_id: string | null;
  run_id: string | null;
  metadata: Record<string, unknown> | null;
  error_category: string | null;
  capture_id: string | null;
  deliveries: AlertDeliveryDetail[];
}
```

### AlertStats

```typescript
export interface AlertStats {
  period: string;
  total_alerts: number;
  by_severity: Record<string, number>;
  by_source: Record<string, number>;
  by_domain: Record<string, number>;
  delivery_success_rate: number;
  avg_delivery_time_ms: number | null;
}
```

---

## Source Types

### Type Enums

```typescript
export type SourceType = "file" | "http" | "database" | "s3" | "sftp";
export type FetchStatus = "SUCCESS" | "FAILED" | "PARTIAL";
export type FetchTrigger = "SCHEDULE" | "MANUAL" | "API" | "DEPENDENCY";
export type DatabaseType = "postgresql" | "db2" | "sqlite" | "mysql" | "oracle";
export type HealthStatus = "HEALTHY" | "UNHEALTHY" | "UNKNOWN";
```

### SourceCreate

```typescript
export interface SourceCreate {
  name: string;
  source_type: SourceType;
  domain?: string;
  config: Record<string, unknown>;
  cron_expression?: string;
  parser_type?: string;
  parser_config?: Record<string, unknown>;
  enabled?: boolean;
}
```

### SourceSummary

```typescript
export interface SourceSummary {
  id: string;
  name: string;
  source_type: SourceType;
  domain: string | null;
  enabled: boolean;
  last_fetch_at: string | null;
  last_fetch_status: FetchStatus | null;
  consecutive_failures: number;
  created_at: string;
}
```

### SourceDetail

```typescript
export interface SourceDetail extends SourceSummary {
  config: Record<string, unknown>;
  cron_expression: string | null;
  next_fetch_at: string | null;
  parser_type: string | null;
  parser_config: Record<string, unknown> | null;
  last_fetch_error: string | null;
  total_fetches: number;
  success_rate: number;
  avg_fetch_duration_ms: number | null;
  last_content_hash: string | null;
  last_etag: string | null;
  last_modified: string | null;
  updated_at: string;
  created_by: string | null;
}
```

### FetchSummary

```typescript
export interface FetchSummary {
  id: string;
  source_id: string;
  status: FetchStatus;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  content_changed: boolean;
  bytes_fetched: number | null;
  rows_parsed: number | null;
}
```

### FetchDetail

```typescript
export interface FetchDetail extends FetchSummary {
  source_name: string;
  trigger: FetchTrigger;
  content_hash: string | null;
  etag: string | null;
  last_modified: string | null;
  error: string | null;
  error_category: string | null;
  triggered_by: string | null;
  execution_id: string | null;
  run_id: string | null;
  capture_id: string | null;
}
```

### DatabaseConnectionResponse

```typescript
export interface DatabaseConnectionResponse {
  id: string;
  name: string;
  db_type: DatabaseType;
  host: string;
  port: number;
  database: string;
  username: string | null;
  pool_size: number;
  pool_overflow: number;
  ssl_mode: string;
  enabled: boolean;
  last_health_check_at: string | null;
  health_status: HealthStatus;
  health_message: string | null;
  active_connections: number;
  idle_connections: number;
  created_at: string;
  updated_at: string;
}
```

---

## List Response Type Aliases

```typescript
export type WorkflowRunListResponse = PaginatedResponse<WorkflowRunSummary>;
export type ScheduleListResponse = PaginatedResponse<ScheduleResponse>;
export type ScheduleRunListResponse = PaginatedResponse<ScheduleRunSummary>;
export type AlertChannelListResponse = PaginatedResponse<AlertChannelResponse>;
export type AlertListResponse = PaginatedResponse<AlertSummary>;
export type SourceListResponse = PaginatedResponse<SourceSummary>;
export type FetchListResponse = PaginatedResponse<FetchSummary>;
export type CacheListResponse = PaginatedResponse<CacheEntry>;
export type DatabaseConnectionListResponse = PaginatedResponse<DatabaseConnectionResponse>;
```

---

## Usage Example

```typescript
import {
  WorkflowRunListResponse,
  WorkflowRunStatus,
  AlertSeverity,
} from '@/api/operationsTypes';

async function fetchFailedWorkflows(): Promise<WorkflowRunListResponse> {
  const response = await fetch('/api/v1/workflows/runs?status=FAILED');
  return response.json();
}

async function sendAlert(
  severity: AlertSeverity,
  title: string,
  message: string
): Promise<void> {
  await fetch('/api/v1/alerts', {
    method: 'POST',
    body: JSON.stringify({ severity, title, message, source: 'frontend' }),
  });
}
```

---

## Notes

1. **Dates**: All dates are ISO 8601 strings. Parse with `new Date(str)` or use a library like `date-fns`.

2. **Nullability**: Many fields are `T | null` to match backend optional responses.

3. **Sensitive Fields**: Config objects may have sensitive fields redacted (e.g., passwords become `"***"`).

4. **Extensibility**: `Record<string, unknown>` is used for config/metadata fields that vary by type.
