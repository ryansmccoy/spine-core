/**
 * Type definitions for Market Spine Operations API
 *
 * These types match the Intermediate tier backend API responses for:
 * - Workflow execution history and management
 * - Schedule management
 * - Alert channels and deliveries
 * - Source registry and fetch history
 *
 * Following FRONTEND_CONTRACT_PRINCIPLES.md patterns.
 */

// ─────────────────────────────────────────────────────────────
// Common Types
// ─────────────────────────────────────────────────────────────

/**
 * Standard pagination metadata matching backend PaginationMeta
 */
export interface PaginationMeta {
  offset: number;
  limit: number;
  total: number;
  has_more: boolean;
}

/**
 * Generic paginated response wrapper
 */
export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta;
}

/**
 * Standard action response for mutations
 */
export interface ActionResponse {
  id: string;
  status: string;
  message: string;
}

// ─────────────────────────────────────────────────────────────
// Workflow Types
// ─────────────────────────────────────────────────────────────

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

/**
 * Summary of a workflow run for list views
 */
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

/**
 * Step execution details within a workflow run
 */
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

/**
 * Full workflow run details with steps
 */
export interface WorkflowRunDetail extends WorkflowRunSummary {
  domain: string | null;
  input_params: Record<string, unknown> | null;
  execution_id: string | null;
  error: string | null;
  error_category: string | null;

  // Metrics
  rows_processed: number | null;

  // Steps
  steps: WorkflowStepDetail[];

  // Context
  triggered_by: string | null;
  parent_run_id: string | null;
  capture_id: string | null;
}

/**
 * Response when triggering a workflow
 */
export interface WorkflowTriggerResponse {
  run_id: string;
  workflow_name: string;
  status: "PENDING" | "STARTED";
  message: string;
}

/**
 * Workflow definition from the registry
 */
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

/**
 * Request to trigger a workflow
 */
export interface WorkflowTriggerRequest {
  params?: Record<string, unknown>;
}

export type WorkflowRunListResponse = PaginatedResponse<WorkflowRunSummary>;

// ─────────────────────────────────────────────────────────────
// Schedule Types
// ─────────────────────────────────────────────────────────────

export type ScheduleTargetType = "PIPELINE" | "WORKFLOW" | "COMMAND";

/**
 * Schedule configuration
 */
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

/**
 * Schedule update request (partial)
 */
export interface ScheduleUpdate {
  description?: string;
  cron_expression?: string;
  interval_seconds?: number;
  target_params?: Record<string, unknown>;
  timezone?: string;
  enabled?: boolean;
  tags?: string[];
}

/**
 * Schedule response (summary and detail share same shape)
 */
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

/**
 * Schedule run history entry
 */
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

/**
 * Next run preview
 */
export interface NextRunPreview {
  schedule_id: string;
  schedule_name: string;
  next_run_at: string;
  cron_expression: string | null;
  interval_seconds: number | null;
}

export type ScheduleListResponse = PaginatedResponse<ScheduleResponse>;
export type ScheduleRunListResponse = PaginatedResponse<ScheduleRunSummary>;

// ─────────────────────────────────────────────────────────────
// Alert Types
// ─────────────────────────────────────────────────────────────

export type AlertSeverity = "INFO" | "WARNING" | "ERROR" | "CRITICAL";
export type AlertChannelType = "slack" | "email" | "servicenow" | "webhook";
export type AlertDeliveryStatus = "PENDING" | "SENT" | "FAILED" | "THROTTLED";

/**
 * Slack channel configuration
 */
export interface ChannelConfigSlack {
  webhook_url: string;
  channel?: string;
  username?: string;
}

/**
 * Email channel configuration
 */
export interface ChannelConfigEmail {
  smtp_host: string;
  smtp_port: number;
  smtp_user?: string;
  from_address: string;
  recipients: string[];
  use_tls?: boolean;
}

/**
 * Request to create an alert channel
 */
export interface AlertChannelCreate {
  name: string;
  channel_type: AlertChannelType;
  config: ChannelConfigSlack | ChannelConfigEmail | Record<string, unknown>;
  min_severity?: AlertSeverity;
  domains?: string[];
  enabled?: boolean;
  throttle_minutes?: number;
}

/**
 * Request to update an alert channel
 */
export interface AlertChannelUpdate {
  config?: Record<string, unknown>;
  min_severity?: AlertSeverity;
  domains?: string[];
  enabled?: boolean;
  throttle_minutes?: number;
}

/**
 * Alert channel response
 */
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

/**
 * Summary of an alert for list views
 */
export interface AlertSummary {
  id: string;
  severity: AlertSeverity;
  title: string;
  source: string;
  domain: string | null;
  created_at: string;

  // Delivery summary
  delivery_count: number;
  success_count: number;
  failed_count: number;
}

/**
 * Alert delivery details
 */
export interface AlertDeliveryDetail {
  id: string;
  channel_id: string;
  channel_name: string;
  status: AlertDeliveryStatus;
  attempted_at: string | null;
  delivered_at: string | null;
  error: string | null;
  attempt: number;
}

/**
 * Full alert details with deliveries
 */
export interface AlertDetail extends AlertSummary {
  message: string;
  execution_id: string | null;
  run_id: string | null;
  metadata: Record<string, unknown> | null;
  error_category: string | null;
  capture_id: string | null;

  deliveries: AlertDeliveryDetail[];
}

/**
 * Request to create a manual alert
 */
export interface AlertCreate {
  severity: AlertSeverity;
  title: string;
  message: string;
  source: string;
  domain?: string;
  metadata?: Record<string, unknown>;
}

/**
 * Alert statistics
 */
export interface AlertStats {
  period: string;
  total_alerts: number;
  by_severity: Record<string, number>;
  by_source: Record<string, number>;
  by_domain: Record<string, number>;
  delivery_success_rate: number;
  avg_delivery_time_ms: number | null;
}

/**
 * Channel test response
 */
export interface ChannelTestResponse {
  channel_id: string;
  channel_name: string;
  success: boolean;
  message: string;
  response?: Record<string, unknown>;
}

export type AlertChannelListResponse = PaginatedResponse<AlertChannelResponse>;
export type AlertListResponse = PaginatedResponse<AlertSummary>;

// ─────────────────────────────────────────────────────────────
// Source Types
// ─────────────────────────────────────────────────────────────

export type SourceType = "file" | "http" | "database" | "s3" | "sftp";
export type FetchStatus = "SUCCESS" | "FAILED" | "PARTIAL";
export type FetchTrigger = "SCHEDULE" | "MANUAL" | "API" | "DEPENDENCY";
export type DatabaseType =
  | "postgresql"
  | "db2"
  | "sqlite"
  | "mysql"
  | "oracle";
export type HealthStatus = "HEALTHY" | "UNHEALTHY" | "UNKNOWN";

/**
 * Request to register a new source
 */
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

/**
 * Request to update a source
 */
export interface SourceUpdate {
  config?: Record<string, unknown>;
  cron_expression?: string;
  parser_type?: string;
  parser_config?: Record<string, unknown>;
  enabled?: boolean;
}

/**
 * Source summary for list views
 */
export interface SourceSummary {
  id: string;
  name: string;
  source_type: SourceType;
  domain: string | null;
  enabled: boolean;

  // Health
  last_fetch_at: string | null;
  last_fetch_status: FetchStatus | null;
  consecutive_failures: number;

  created_at: string;
}

/**
 * Full source details
 */
export interface SourceDetail extends SourceSummary {
  config: Record<string, unknown>; // Sensitive fields redacted

  // Scheduling
  cron_expression: string | null;
  next_fetch_at: string | null;

  // Parse settings
  parser_type: string | null;
  parser_config: Record<string, unknown> | null;

  // Health
  last_fetch_error: string | null;

  // Stats
  total_fetches: number;
  success_rate: number;
  avg_fetch_duration_ms: number | null;

  // Change detection
  last_content_hash: string | null;
  last_etag: string | null;
  last_modified: string | null;

  // Audit
  updated_at: string;
  created_by: string | null;
}

/**
 * Summary of a fetch operation
 */
export interface FetchSummary {
  id: string;
  source_id: string;
  status: FetchStatus;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;

  // Change detection
  content_changed: boolean;

  // Metrics
  bytes_fetched: number | null;
  rows_parsed: number | null;
}

/**
 * Full fetch operation details
 */
export interface FetchDetail extends FetchSummary {
  source_name: string;
  trigger: FetchTrigger;

  // Change detection
  content_hash: string | null;
  etag: string | null;
  last_modified: string | null;

  // Errors
  error: string | null;
  error_category: string | null;

  // Context
  triggered_by: string | null;
  execution_id: string | null;
  run_id: string | null;
  capture_id: string | null;
}

/**
 * Response when triggering a fetch
 */
export interface FetchTriggerResponse {
  fetch_id: string;
  source_id: string;
  source_name: string;
  status: "PENDING" | "STARTED";
  message: string;
}

/**
 * Cache entry
 */
export interface CacheEntry {
  id: string;
  source_id: string;
  source_name: string;
  cache_key: string;
  content_hash: string;
  size_bytes: number;
  cached_at: string;
  expires_at: string | null;
  fetch_id: string | null;
  content_type: string | null;
  encoding: string | null;
}

/**
 * Cache statistics
 */
export interface CacheStats {
  total_entries: number;
  total_bytes: number;
  hit_rate: number;
  miss_rate: number;
  expired_entries: number;
  by_source: Record<string, number>;
}

/**
 * Database connection configuration
 */
export interface DatabaseConnectionCreate {
  name: string;
  db_type: DatabaseType;
  host: string;
  port: number;
  database: string;
  username?: string;
  password_ref?: string;
  pool_size?: number;
  pool_overflow?: number;
  ssl_mode?: "disable" | "require" | "verify-ca" | "verify-full";
  ssl_cert_ref?: string;
  enabled?: boolean;
}

/**
 * Database connection response
 */
export interface DatabaseConnectionResponse {
  id: string;
  name: string;
  db_type: DatabaseType;
  host: string;
  port: number;
  database: string;
  username: string | null;

  // Pool
  pool_size: number;
  pool_overflow: number;

  // SSL
  ssl_mode: string;

  enabled: boolean;

  // Health
  last_health_check_at: string | null;
  health_status: HealthStatus;
  health_message: string | null;

  // Stats
  active_connections: number;
  idle_connections: number;

  // Audit
  created_at: string;
  updated_at: string;
}

export type SourceListResponse = PaginatedResponse<SourceSummary>;
export type FetchListResponse = PaginatedResponse<FetchSummary>;
export type CacheListResponse = PaginatedResponse<CacheEntry>;
export type DatabaseConnectionListResponse =
  PaginatedResponse<DatabaseConnectionResponse>;
