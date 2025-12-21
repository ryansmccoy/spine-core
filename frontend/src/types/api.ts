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
