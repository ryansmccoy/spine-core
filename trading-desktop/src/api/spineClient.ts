/**
 * Market Spine API Client
 * 
 * Unified client for Market Spine Basic/Intermediate/Full backends.
 * Uses /v1/capabilities to determine available features.
 */

import type {
  HealthResponse,
  CapabilitiesResponse,
  SpineCapabilities,
  ListPipelinesResponse,
  PipelineDetail,
  RunPipelineRequest,
  ExecutionResponse,
  QueryWeeksResponse,
  QuerySymbolsResponse,
  QuerySymbolHistoryResponse,
  StorageStatsResponse,
  CapturesListResponse,
  PriceDataResponse,
  PriceLatestResponse,
  DataTier,
  RequestOptions,
  OTCWeeklyData,
  SymbolInfo,
} from './spineTypes';
import { SpineError } from './spineTypes';

// ─────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────

export interface SpineClientConfig {
  /** Base URL for the API (e.g., 'http://localhost:8001') */
  baseUrl?: string;
  /** Request timeout in milliseconds */
  timeout?: number;
  /** Enable request ID generation */
  enableTracing?: boolean;
}

const DEFAULT_CONFIG: Required<SpineClientConfig> = {
  baseUrl: '',
  timeout: 30000,
  enableTracing: true,
};

// ─────────────────────────────────────────────────────────────
// Spine Client
// ─────────────────────────────────────────────────────────────

export class SpineClient {
  private config: Required<SpineClientConfig>;
  private cachedCapabilities: SpineCapabilities | null = null;

  constructor(config: SpineClientConfig = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  // ───────────────────────────────────────────────────────────
  // Core Request Method
  // ───────────────────────────────────────────────────────────

  private async request<T>(
    method: 'GET' | 'POST' | 'PUT' | 'DELETE',
    path: string,
    body?: unknown,
    options?: RequestOptions
  ): Promise<T> {
    const url = `${this.config.baseUrl}${path}`;
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      ...options?.headers,
    };

    // Add tracing header
    if (this.config.enableTracing) {
      headers['x-request-id'] = options?.requestId ?? this.generateRequestId();
    }

    // Create abort controller for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.config.timeout);

    try {
      const response = await fetch(url, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: options?.signal ?? controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        
        // Handle FastAPI error format
        if (errorBody.detail) {
          const detail = typeof errorBody.detail === 'object' 
            ? errorBody.detail 
            : { message: errorBody.detail };
          
          throw new SpineError(
            {
              code: detail.error?.code ?? `HTTP_${response.status}`,
              message: detail.error?.message ?? detail.message ?? response.statusText,
              details: detail.error?.details ?? detail,
            },
            response.status
          );
        }

        throw new SpineError(
          {
            code: `HTTP_${response.status}`,
            message: errorBody.message ?? response.statusText,
            details: errorBody,
          },
          response.status
        );
      }

      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof SpineError) {
        throw error;
      }

      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new SpineError({
          code: 'REQUEST_TIMEOUT',
          message: `Request timed out after ${this.config.timeout}ms`,
        });
      }

      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new SpineError({
          code: 'NETWORK_ERROR',
          message: 'Unable to connect to Market Spine backend',
          details: { originalError: error.message },
        });
      }

      throw new SpineError({
        code: 'UNKNOWN_ERROR',
        message: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  }

  private generateRequestId(): string {
    return `ui-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  // ───────────────────────────────────────────────────────────
  // Health Endpoints
  // ───────────────────────────────────────────────────────────

  /**
   * Check if the backend is reachable (basic health check)
   */
  async getHealth(options?: RequestOptions): Promise<HealthResponse> {
    return this.request<HealthResponse>('GET', '/health', undefined, options);
  }

  /**
   * Get detailed health including component checks
   */
  async getHealthDetailed(options?: RequestOptions): Promise<HealthResponse> {
    return this.request<HealthResponse>('GET', '/health/detailed', undefined, options);
  }

  // ───────────────────────────────────────────────────────────
  // Capabilities Discovery
  // ───────────────────────────────────────────────────────────

  /**
   * Get raw capabilities response from the backend
   */
  async getCapabilitiesRaw(options?: RequestOptions): Promise<CapabilitiesResponse> {
    return this.request<CapabilitiesResponse>('GET', '/v1/capabilities', undefined, options);
  }

  /**
   * Get capabilities with derived feature flags.
   * Results are cached for the session.
   */
  async getCapabilities(options?: RequestOptions): Promise<SpineCapabilities> {
    if (this.cachedCapabilities) {
      return this.cachedCapabilities;
    }

    const raw = await this.getCapabilitiesRaw(options);
    
    this.cachedCapabilities = {
      ...raw,
      // Derived capabilities for UI gating
      hasAsyncExecution: raw.async_execution,
      hasExecutionHistory: raw.execution_history,
      hasScheduling: raw.scheduling,
      hasQueues: raw.tier !== 'basic', // Queues available in intermediate+
      hasIncidents: raw.tier === 'full', // Incidents only in full
      hasOrchestratorLab: raw.async_execution, // Lab needs async execution
      hasDataLineage: raw.tier !== 'basic', // Lineage in intermediate+
    };

    return this.cachedCapabilities;
  }

  /**
   * Clear cached capabilities (e.g., on backend change)
   */
  clearCapabilitiesCache(): void {
    this.cachedCapabilities = null;
  }

  // ───────────────────────────────────────────────────────────
  // Pipeline Endpoints
  // ───────────────────────────────────────────────────────────

  /**
   * List available pipelines
   * @param prefix Optional filter by name prefix
   */
  async listPipelines(prefix?: string, options?: RequestOptions): Promise<ListPipelinesResponse> {
    const query = prefix ? `?prefix=${encodeURIComponent(prefix)}` : '';
    return this.request<ListPipelinesResponse>('GET', `/v1/pipelines${query}`, undefined, options);
  }

  /**
   * Get detailed information about a pipeline
   * @param name Pipeline name (e.g., 'finra.otc_transparency.ingest')
   */
  async describePipeline(name: string, options?: RequestOptions): Promise<PipelineDetail> {
    return this.request<PipelineDetail>('GET', `/v1/pipelines/${encodeURIComponent(name)}`, undefined, options);
  }

  /**
   * Execute a pipeline
   * @param name Pipeline name
   * @param request Execution parameters
   */
  async runPipeline(
    name: string,
    request?: RunPipelineRequest,
    options?: RequestOptions
  ): Promise<ExecutionResponse> {
    return this.request<ExecutionResponse>(
      'POST',
      `/v1/pipelines/${encodeURIComponent(name)}/run`,
      {
        params: request?.params ?? {},
        dry_run: request?.dry_run ?? false,
        lane: request?.lane ?? 'default',
      },
      options
    );
  }

  // ───────────────────────────────────────────────────────────
  // Data Query Endpoints
  // ───────────────────────────────────────────────────────────

  /**
   * Query available weeks of data for a tier
   * @param tier Data tier (OTC, NMS_TIER_1, NMS_TIER_2)
   * @param limit Max weeks to return (1-100)
   */
  async queryWeeks(tier: DataTier, limit: number = 10, options?: RequestOptions): Promise<QueryWeeksResponse> {
    const query = new URLSearchParams({
      tier,
      limit: String(Math.min(Math.max(1, limit), 100)),
    });
    return this.request<QueryWeeksResponse>('GET', `/v1/data/weeks?${query}`, undefined, options);
  }

  /**
   * Query top symbols by volume for a specific week
   * @param tier Data tier
   * @param week Week ending date (YYYY-MM-DD)
   * @param top Number of symbols to return
   */
  async querySymbols(
    tier: DataTier,
    week: string,
    top: number = 10,
    options?: RequestOptions
  ): Promise<QuerySymbolsResponse> {
    const query = new URLSearchParams({
      tier,
      week,
      top: String(Math.min(Math.max(1, top), 100)),
    });
    return this.request<QuerySymbolsResponse>('GET', `/v1/data/symbols?${query}`, undefined, options);
  }

  // ───────────────────────────────────────────────────────────
  // OTC Data Helpers (Trading Desktop)
  // ───────────────────────────────────────────────────────────

  /**
   * Get top OTC symbols across all tiers for the latest week.
   * This is a convenience method that queries the latest week first.
   * 
   * @param limit Number of top symbols
   * @param tier Default tier to use (OTC is most comprehensive)
   */
  async getTopOTCSymbols(
    limit: number = 15,
    tier: DataTier = 'OTC',
    options?: RequestOptions
  ): Promise<OTCWeeklyData[]> {
    // First get the latest week
    const weeksResult = await this.queryWeeks(tier, 1, options);
    
    if (weeksResult.weeks.length === 0) {
      return [];
    }
    
    const latestWeek = weeksResult.weeks[0].week_ending;
    const symbolsResult = await this.querySymbols(tier, latestWeek, limit, options);
    
    // Map to OTCWeeklyData format
    return symbolsResult.symbols.map((s: SymbolInfo, index: number): OTCWeeklyData => ({
      week_ending: latestWeek,
      symbol: s.symbol,
      total_volume: s.volume,
      trade_count: null,  // Not available in basic response
      rank: index + 1,
      wow_change: null,   // Would need historical data
      avg_volume_6w: null, // Would need historical data
    }));
  }

  /**
   * Get historical trading data for a specific symbol.
   *
   * Returns weekly trading data sorted chronologically (oldest to newest)
   * for charting purposes.
   *
   * @param symbol Trading symbol
   * @param tier Data tier
   * @param weeks Number of weeks of history (default 12, max 52)
   */
  async getSymbolHistory(
    symbol: string,
    tier: DataTier = 'OTC',
    weeks: number = 12,
    options?: RequestOptions
  ): Promise<QuerySymbolHistoryResponse> {
    const query = new URLSearchParams({
      tier,
      weeks: Math.min(weeks, 52).toString(),
    });
    return this.request<QuerySymbolHistoryResponse>(
      'GET',
      `/v1/data/symbols/${encodeURIComponent(symbol)}/history?${query}`,
      undefined,
      options
    );
  }

  /**
   * Get OTC data for a specific symbol (latest week only in Basic tier).
   * 
   * @param symbol Trading symbol
   * @param tier Data tier
   */
  async getSymbolOTCData(
    symbol: string,
    tier: DataTier = 'OTC',
    options?: RequestOptions
  ): Promise<OTCWeeklyData | null> {
    // Get the latest week
    const weeksResult = await this.queryWeeks(tier, 1, options);
    
    if (weeksResult.weeks.length === 0) {
      return null;
    }
    
    const latestWeek = weeksResult.weeks[0].week_ending;
    
    // Query all symbols to find this one (inefficient, but works for Basic tier)
    const symbolsResult = await this.querySymbols(tier, latestWeek, 100, options);
    const found = symbolsResult.symbols.find(
      s => s.symbol.toUpperCase() === symbol.toUpperCase()
    );
    
    if (!found) {
      return null;
    }
    
    const rank = symbolsResult.symbols.findIndex(
      s => s.symbol.toUpperCase() === symbol.toUpperCase()
    ) + 1;
    
    return {
      week_ending: latestWeek,
      symbol: found.symbol,
      total_volume: found.volume,
      trade_count: null,
      rank,
      wow_change: null,
      avg_volume_6w: null,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // Operations Endpoints
  // ─────────────────────────────────────────────────────────────

  /**
   * Get storage statistics.
   *
   * Returns database size, table row counts, and storage metrics.
   */
  async getStorageStats(options?: RequestOptions): Promise<StorageStatsResponse> {
    return this.request<StorageStatsResponse>('GET', '/v1/ops/storage', undefined, options);
  }

  /**
   * List all data captures.
   *
   * Returns capture IDs with their associated metadata including
   * the tier, week ending date, capture timestamp, and row counts.
   */
  async listCaptures(options?: RequestOptions): Promise<CapturesListResponse> {
    return this.request<CapturesListResponse>('GET', '/v1/ops/captures', undefined, options);
  }

  // ─────────────────────────────────────────────────────────────
  // Price Data Endpoints
  // ─────────────────────────────────────────────────────────────

  /**
   * Get price history for a symbol.
   *
   * Returns daily OHLCV price data, ordered by date descending.
   *
   * @param symbol Stock ticker symbol
   * @param days Number of days of history (1-365, default 30)
   */
  async getPrices(
    symbol: string,
    days: number = 30,
    options?: RequestOptions
  ): Promise<PriceDataResponse> {
    return this.request<PriceDataResponse>(
      'GET',
      `/v1/data/prices/${encodeURIComponent(symbol)}?days=${days}`,
      undefined,
      options
    );
  }

  /**
   * Get the latest price for a symbol.
   *
   * Returns the most recent available price data.
   *
   * @param symbol Stock ticker symbol
   */
  async getLatestPrice(
    symbol: string,
    options?: RequestOptions
  ): Promise<PriceLatestResponse> {
    return this.request<PriceLatestResponse>(
      'GET',
      `/v1/data/prices/${encodeURIComponent(symbol)}/latest`,
      undefined,
      options
    );
  }
}

// ─────────────────────────────────────────────────────────────
// Default Client Instance
// ─────────────────────────────────────────────────────────────

/**
 * Create client from environment variables
 */
export function createSpineClient(): SpineClient {
  const baseUrl = import.meta.env.VITE_MARKET_SPINE_URL ?? '';
  const enableTracing = import.meta.env.VITE_ENABLE_TRACING !== 'false';
  
  return new SpineClient({
    baseUrl,
    enableTracing,
  });
}

/** Default client instance */
export const spineClient = createSpineClient();
