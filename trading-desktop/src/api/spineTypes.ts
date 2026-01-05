/**
 * Type definitions for Market Spine API
 * 
 * These types match the Basic backend API responses and are forward-compatible
 * with Intermediate and Full tiers.
 */

// ─────────────────────────────────────────────────────────────
// API Error Types
// ─────────────────────────────────────────────────────────────

export interface SpineApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export class SpineError extends Error {
  public readonly code: string;
  public readonly details?: Record<string, unknown>;
  public readonly httpStatus?: number;

  constructor(error: SpineApiError, httpStatus?: number) {
    super(error.message);
    this.name = 'SpineError';
    this.code = error.code;
    this.details = error.details;
    this.httpStatus = httpStatus;
  }
}

// ─────────────────────────────────────────────────────────────
// Health Types
// ─────────────────────────────────────────────────────────────

export type HealthStatus = 'ok' | 'error' | 'warning';

export interface ComponentHealth {
  name: string;
  status: HealthStatus;
  message: string;
  latency_ms?: number;
}

export interface HealthResponse {
  status: HealthStatus;
  timestamp: string;
  checks?: ComponentHealth[];
  details?: Record<string, unknown>;
}

// ─────────────────────────────────────────────────────────────
// Capabilities Types
// ─────────────────────────────────────────────────────────────

export type SpineTier = 'basic' | 'intermediate' | 'full';

export interface CapabilitiesResponse {
  api_version: string;
  tier: SpineTier;
  version: string;
  sync_execution: boolean;
  async_execution: boolean;
  execution_history: boolean;
  authentication: boolean;
  scheduling: boolean;
  rate_limiting: boolean;
  webhook_notifications: boolean;
}

/**
 * Derived capabilities for UI feature gating
 */
export interface SpineCapabilities extends CapabilitiesResponse {
  // Computed feature flags
  hasAsyncExecution: boolean;
  hasExecutionHistory: boolean;
  hasScheduling: boolean;
  hasQueues: boolean;
  hasIncidents: boolean;
  hasOrchestratorLab: boolean;
  hasDataLineage: boolean;
}

// ─────────────────────────────────────────────────────────────
// Pipeline Types
// ─────────────────────────────────────────────────────────────

export interface PipelineSummary {
  name: string;
  description: string;
}

export interface ListPipelinesResponse {
  pipelines: PipelineSummary[];
  count: number;
}

export interface ParameterDef {
  name: string;
  type: string;
  description: string;
  default?: unknown;
  required: boolean;
  choices?: string[];
}

export interface PipelineDetail {
  name: string;
  description: string;
  required_params: ParameterDef[];
  optional_params: ParameterDef[];
  is_ingest: boolean;
}

export interface RunPipelineRequest {
  params?: Record<string, unknown>;
  dry_run?: boolean;
  lane?: 'default' | 'normal' | 'backfill' | 'slow';
}

export type ExecutionStatus = 'completed' | 'failed' | 'dry_run' | 'running' | 'pending';

export interface ExecutionResponse {
  execution_id: string;
  pipeline: string;
  status: ExecutionStatus;
  rows_processed?: number | null;
  duration_seconds?: number | null;
  poll_url?: string | null;
}

// ─────────────────────────────────────────────────────────────
// Data Query Types
// ─────────────────────────────────────────────────────────────

export type DataTier = 'OTC' | 'NMS_TIER_1' | 'NMS_TIER_2';

export interface WeekInfo {
  week_ending: string;
  symbol_count: number;
}

export interface QueryWeeksResponse {
  tier: string;
  weeks: WeekInfo[];
  count: number;
}

export interface SymbolInfo {
  symbol: string;
  volume: number;
  avg_price?: number | null;
}

export interface QuerySymbolsResponse {
  tier: string;
  week: string;
  symbols: SymbolInfo[];
  count: number;
}

export interface SymbolWeekData {
  week_ending: string;
  total_shares: number;
  total_trades: number;
  average_price: number | null;
}

export interface QuerySymbolHistoryResponse {
  symbol: string;
  tier: string;
  history: SymbolWeekData[];
  count: number;
}

// ─────────────────────────────────────────────────────────────
// Ops/Storage Types
// ─────────────────────────────────────────────────────────────

export interface TableStats {
  name: string;
  row_count: number;
  size_bytes: number | null;
}

export interface StorageStatsResponse {
  database_path: string;
  database_size_bytes: number;
  tables: TableStats[];
  total_rows: number;
}

export interface CaptureInfo {
  capture_id: string;
  captured_at: string | null;
  tier: string;
  week_ending: string;
  row_count: number;
}

export interface CapturesListResponse {
  captures: CaptureInfo[];
  count: number;
}

// ─────────────────────────────────────────────────────────────
// Price Data Types
// ─────────────────────────────────────────────────────────────

/**
 * Single price candle (OHLCV data)
 */
export interface PriceCandle {
  symbol: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change: number | null;
  change_percent: number | null;
}

/**
 * Response for price history query
 */
export interface PriceDataResponse {
  symbol: string;
  source: string;
  count: number;
  candles: PriceCandle[];
  capture_id: string | null;
  captured_at: string | null;
}

/**
 * Response for latest price query
 */
export interface PriceLatestResponse {
  symbol: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change: number | null;
  change_percent: number | null;
  source: string;
  captured_at: string | null;
}

// ─────────────────────────────────────────────────────────────
// OTC Data Types (Trading Desktop)
// ─────────────────────────────────────────────────────────────

/**
 * Normalized OTC weekly data for the Trading Desktop widgets.
 * Maps from QuerySymbolsResponse with computed fields.
 */
export interface OTCWeeklyData {
  week_ending: string;
  symbol: string;
  total_volume: number;
  trade_count: number | null;
  rank: number;
  // Computed fields - may be null if insufficient data
  wow_change: number | null;
  avg_volume_6w: number | null;
}

/**
 * Data availability status for features not in Basic tier
 */
export interface FeatureUnavailable {
  available: false;
  message: string;
  requiredTier: SpineTier;
}

export type DataResult<T> = { available: true; data: T } | FeatureUnavailable;

// ─────────────────────────────────────────────────────────────
// Request Options
// ─────────────────────────────────────────────────────────────

export interface RequestOptions {
  /** Optional request ID for tracing */
  requestId?: string;
  /** Abort signal for cancellation */
  signal?: AbortSignal;
  /** Custom headers */
  headers?: Record<string, string>;
}
