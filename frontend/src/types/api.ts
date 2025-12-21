/** TypeScript types matching spine-core API Pydantic schemas. */

// ── Envelope types ──────────────────────────────────────────────────

export interface PageMeta {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface PagedResponse<T> {
  data: T[];
  page: PageMeta;
  elapsed_ms?: number;
  warnings?: string[];
}

export interface SuccessResponse<T> {
  data: T;
  elapsed_ms?: number;
  warnings?: string[];
}

export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
}

// ── Health / Capabilities ───────────────────────────────────────────

export interface HealthStatus {
  status: string;
  database: Record<string, unknown>;
  checks: Record<string, unknown>;
  version: string;
}

export interface Capabilities {
  tier: string;
  sync_execution: boolean;
  async_execution: boolean;
  scheduling: boolean;
  rate_limiting: boolean;
  execution_history: boolean;
  dlq: boolean;
}

// ── Database ────────────────────────────────────────────────────────

export interface DatabaseInit {
  tables_created: string[];
  dry_run: boolean;
}

export interface TableCount {
  table: string;
  count: number;
}

export interface DatabaseHealth {
  connected: boolean;
  backend: string;
  table_count: number;
  latency_ms: number;
}

export interface PurgeResult {
  rows_deleted: number;
  tables_purged: string[];
  dry_run: boolean;
}

export interface DatabaseConfig {
  backend: string;
  url_masked: string;
  data_dir: string;
  is_persistent: boolean;
  file_path: string | null;
  file_size_mb: number | null;
  tier: string;
  env_file_hint: string;
}

export interface TableSchemaColumn {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  default: string | null;
}

export interface TableSchema {
  table_name: string;
  columns: TableSchemaColumn[];
  row_count: number;
  indexes: string[];
}

export interface QueryResponse {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
}

export interface VacuumResponse {
  success: boolean;
  size_before_mb: number | null;
  size_after_mb: number | null;
  space_reclaimed_mb: number | null;
  message: string;
}

export interface BackupResponse {
  success: boolean;
  backup_path: string | null;
  size_mb: number | null;
  message: string;
}

// ── Runs ────────────────────────────────────────────────────────────

export interface RunSummary {
  run_id: string;
  pipeline: string | null;
  workflow: string | null;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
}

export interface RunDetail extends RunSummary {
  params: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: string | null;
  events: Record<string, unknown>[];
}

export interface RunAccepted {
  run_id: string;
  dry_run: boolean;
  would_execute: boolean;
}

export interface RunEvent {
  event_id: string;
  run_id: string;
  event_type: string;
  timestamp: string;
  data: Record<string, unknown>;
  message: string;
}

export interface SubmitRunRequest {
  kind: 'task' | 'pipeline' | 'workflow';
  name: string;
  params?: Record<string, unknown>;
  idempotency_key?: string;
  priority?: string;
  metadata?: Record<string, unknown>;
}

// ── Workflows ───────────────────────────────────────────────────────

export interface WorkflowSummary {
  name: string;
  step_count: number;
  description: string;
}

export interface ExecutionPolicy {
  mode: string;
  max_concurrency: number;
  on_failure: string;
  timeout_minutes: number | null;
}

export interface WorkflowStep {
  name: string;
  description: string;
  pipeline: string;
  depends_on: string[];
  params: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface WorkflowDetail {
  name: string;
  steps: WorkflowStep[];
  description: string;
  domain: string;
  version: number;
  policy: ExecutionPolicy;
  tags: string[];
  defaults: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface RunWorkflowRequest {
  params?: Record<string, unknown>;
  idempotency_key?: string;
  dry_run?: boolean;
}

// ── Schedules ───────────────────────────────────────────────────────

export interface ScheduleSummary {
  schedule_id: string;
  workflow_name: string;
  cron: string;
  interval_seconds: number | null;
  enabled: boolean;
  next_run: string;
}

export interface ScheduleDetail extends ScheduleSummary {
  params: Record<string, unknown>;
  last_run: string;
  run_count: number;
  created_at: string;
}

export interface CreateScheduleRequest {
  workflow_name: string;
  cron?: string;
  interval_seconds?: number;
  params?: Record<string, unknown>;
  enabled?: boolean;
}

export interface UpdateScheduleRequest {
  cron?: string;
  interval_seconds?: number;
  enabled?: boolean;
  params?: Record<string, unknown>;
}

// ── DLQ ─────────────────────────────────────────────────────────────

export interface DeadLetter {
  id: string;
  pipeline: string;
  error: string;
  created_at: string;
  replay_count: number;
}

// ── Quality ─────────────────────────────────────────────────────────

export interface QualityResult {
  pipeline: string;
  checks_passed: number;
  checks_failed: number;
  score: number;
  run_at: string;
}

// ── Anomaly ─────────────────────────────────────────────────────────

export interface Anomaly {
  id: string;
  pipeline: string;
  metric: string;
  severity: string;
  value: number;
  threshold: number;
  detected_at: string;
}

// ── Examples ────────────────────────────────────────────────────────

export interface ExampleItem {
  category: string;
  name: string;
  title: string;
  description: string;
  order: number;
}

export interface ExampleRunResult {
  name: string;
  category: string;
  title: string;
  status: string;
  duration_seconds: number;
  stdout_tail: string[];
}

export interface ExamplesSummary {
  total: number;
  passed: number;
  failed: number;
  categories: string[];
  last_run_at: string | null;
  examples: ExampleRunResult[];
}

export interface RunExamplesResponse {
  status: string;
  message: string;
  pid: number | null;
}

export interface ExampleSource {
  name: string;
  title: string;
  description: string;
  source: string;
  path: string;
  line_count: number;
  language: string;
}

// ── Playground ──────────────────────────────────────────────────────

export interface PlaygroundSession {
  session_id: string;
  workflow_name: string;
  total_steps: number;
  executed: number;
  remaining: number;
  is_complete: boolean;
  created_at: number;
  last_accessed: number;
}

export interface StepSnapshot {
  step_name: string;
  step_type: string;
  status: 'completed' | 'failed' | 'skipped';
  result: {
    success: boolean;
    output: Record<string, unknown> | null;
    error: string | null;
  } | null;
  context_before: Record<string, unknown>;
  context_after: Record<string, unknown>;
  duration_ms: number;
  error: string | null;
  step_index: number;
}

export interface StepPreview {
  name: string;
  step_type: string;
  pipeline_name: string | null;
  depends_on: string[];
  config: Record<string, unknown>;
}

export interface ContextSnapshot {
  run_id: string;
  workflow_name: string;
  params: Record<string, unknown>;
  outputs: Record<string, unknown>;
}

export interface PlaygroundWorkflow {
  name: string;
  description: string;
  step_count: number;
  domain: string;
  tags: string[];
  steps: Array<{
    name: string;
    type: string;
    pipeline: string | null;
    depends_on: string[];
  }>;
}

export interface PlaygroundExample {
  id: string;
  title: string;
  description: string;
  workflow_name: string;
  params: Record<string, unknown>;
  code_snippet: string;
  category: string;
}

export interface CreateSessionRequest {
  workflow_name: string;
  params?: Record<string, unknown>;
}

export interface SetParamsRequest {
  params: Record<string, unknown>;
}

// ── Run Steps ───────────────────────────────────────────────────────

export interface RunStep {
  step_id: string;
  run_id: string;
  step_name: string;
  step_type: string;
  step_order: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  row_count: number | null;
  attempt: number;
  max_attempts: number;
  error: string | null;
  error_category: string | null;
  metrics: Record<string, unknown>;
}

// ── Run Logs ────────────────────────────────────────────────────────

export interface RunLogEntry {
  timestamp: string;
  level: string;
  message: string;
  step_name: string | null;
  logger: string;
  line_number: number;
}

// ── Run History (Activity Chart) ────────────────────────────────────

export interface RunHistoryBucket {
  bucket: string;
  completed: number;
  failed: number;
  running: number;
  cancelled: number;
}

export interface RunToRequest {
  step_name: string;
}

// ── Functions (AWS Lambda-inspired) ─────────────────────────────────

export interface FunctionConfig {
  timeout: number;
  memory_mb: number;
  runtime: string;
  env_vars: Record<string, string>;
  handler: string;
}

export interface FunctionSummary {
  id: string;
  name: string;
  description: string;
  runtime: string;
  handler: string;
  timeout: number;
  memory_mb: number;
  tags: string[];
  source_lines: number;
  last_modified: string;
  last_invoked: string | null;
  invoke_count: number;
  status: string;
}

export interface FunctionDetail {
  id: string;
  name: string;
  description: string;
  source: string;
  config: FunctionConfig;
  tags: string[];
  created_at: string;
  last_modified: string;
  last_invoked: string | null;
  invoke_count: number;
  status: string;
  last_result: Record<string, unknown> | null;
}

export interface FunctionCreateRequest {
  name: string;
  description?: string;
  source?: string;
  config?: Partial<FunctionConfig>;
  tags?: string[];
}

export interface FunctionUpdateRequest {
  name?: string;
  description?: string;
  source?: string;
  config?: FunctionConfig;
  tags?: string[];
}

export interface InvokeRequest {
  event?: Record<string, unknown>;
  context?: Record<string, unknown>;
  timeout?: number;
  dry_run?: boolean;
}

export interface InvokeResult {
  request_id: string;
  function_id: string;
  function_name: string;
  status: string;
  result: unknown;
  logs: string;
  error: string | null;
  error_type: string | null;
  duration_ms: number;
  billed_duration_ms: number;
  memory_used_mb: number | null;
  started_at: string;
  ended_at: string;
}

export interface InvocationLog {
  request_id: string;
  timestamp: string;
  status: string;
  duration_ms: number;
  error: string | null;
  event_summary: string;
}

export interface FunctionTemplate {
  id: string;
  name: string;
  description: string;
  source: string;
  config: FunctionConfig;
  tags: string[];
  category: string;
}
