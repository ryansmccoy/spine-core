# Frontend ↔ Backend Integration Map

> Generated: 2026-01-04  
> Status: **IMPLEMENTED**  
> Scope: Market Spine Trading Desktop → Market Spine Basic API

## Summary

The trading-desktop frontend was originally built for an older Market Spine backend with a different API surface. This document maps the frontend's expectations to what Basic provides and defines the adaptation strategy.

### Implementation Status

| Task | Status |
|------|--------|
| Inventory & Map | ✅ Complete |
| Capabilities-Driven Design | ✅ Complete |
| Thin API Client Layer | ✅ Complete |
| Vertical Slices (Health, Pipelines, Data) | ✅ Complete |
| Dev Support (proxy, env) | ✅ Complete |
| Tests | ✅ 36 passing |
| Docs | ✅ Complete |

### Files Created

| File | Purpose |
|------|---------|
| `src/api/spineTypes.ts` | TypeScript types for Basic API |
| `src/api/spineClient.ts` | Unified API client with error handling |
| `src/api/spineContext.tsx` | React context, hooks, and FeatureGate |
| `src/api/__tests__/spineClient.test.ts` | Client unit tests |
| `src/api/__tests__/spineContext.test.ts` | Context logic tests |
| `src/test/setup.ts` | Vitest setup |
| `vitest.config.ts` | Test configuration |
| `.env.local.example` | Environment template |
| `docs/frontend-setup.md` | Setup guide |

### Files Modified

| File | Changes |
|------|---------|
| `src/main.tsx` | Wrapped app with SpineProvider |
| `src/api/index.ts` | Export new spine modules |
| `src/dashboard/DashboardLayout.tsx` | Added connection banner, tier-based nav |
| `src/dashboard/pages/OverviewPage.tsx` | Real health/pipeline data |
| `src/dashboard/pages/PipelinesPage.tsx` | Spine client integration |
| `src/dashboard/pages/DataAssetsPage.tsx` | Weeks/symbols queries |
| `src/dashboard/pages/JobsPage.tsx` | Tier upgrade message |
| `src/dashboard/pages/QueuesPage.tsx` | Tier upgrade message |
| `src/dashboard/pages/IncidentsPage.tsx` | Tier upgrade message |
| `src/dashboard/pages/orchestrator/*.tsx` | Tier upgrade messages |
| `src/index.css` | Connection banner styles |
| `package.json` | Added test scripts & dependencies |
| `vite.config.ts` | Added proxy configuration |
| `README.md` | Added Frontend ↔ Backend section |

---

## 1. Frontend API Clients Inventory

### 1.1 Main API Client (`src/api/client.ts`)

**Base URL**: `VITE_API_URL` env var (defaults to empty string, uses relative paths)

| Method | Endpoint Expected | Payload Shape | Purpose |
|--------|-------------------|---------------|---------|
| `query<T>()` | `POST /api/v1/query` | `{ dataset, symbol?, symbols?, start_date?, end_date?, limit? }` | Generic query for all datasets |
| `getSymbols()` | Uses query: `{ dataset: 'symbols' }` | — | List tradeable symbols |
| `getPrices()` | Uses query: `{ dataset: 'prices', symbol, start_date }` | — | OHLCV price data |
| `getOTCData()` | Uses query: `{ dataset: 'otc_transparency', symbol }` | — | OTC weekly data for symbol |
| `getOTCTopVolume()` | Uses query: `{ dataset: 'otc_top_volume' }` | — | Top OTC movers |
| `getVenues()` | Uses query: `{ dataset: 'venues', symbol }` | — | Venue execution scores |
| `getLiquidity()` | Uses query: `{ dataset: 'liquidity', symbol }` | — | Spread/depth data |

### 1.2 Dashboard API Client (`src/dashboard/api/index.ts`)

| Method | Endpoint Expected | Purpose |
|--------|-------------------|---------|
| `getSystemHealth()` | `GET /api/v1/dashboard/health` | System status |
| `getExecutionsSummary()` | `GET /api/v1/dashboard/executions/summary` | Running/failed counts |
| `getExecutions()` | `GET /api/v1/dashboard/executions` | List executions |
| `getExecution(id)` | `GET /api/v1/dashboard/executions/{id}` | Execution details |
| `getPipelines()` | `GET /api/v1/dashboard/pipelines` | Pipeline list |
| `getPipeline(id)` | `GET /api/v1/dashboard/pipelines/{id}` | Pipeline details |
| `triggerPipeline(id)` | `POST /api/v1/dashboard/pipelines/{id}/trigger` | Run pipeline |
| `getQueuesStats()` | `GET /api/v1/dashboard/queues` | Queue depths |
| `getIncidents()` | `GET /api/v1/dashboard/incidents` | Incident list |
| `getRecentFailures()` | `GET /api/v1/dashboard/failures` | Recent failures |
| `retryExecution(id)` | `POST /api/v1/dashboard/executions/{id}/retry` | Retry failed |
| `cancelExecution(id)` | `POST /api/v1/dashboard/executions/{id}/cancel` | Cancel running |

### 1.3 Orchestrator Lab Client (`src/api/orchestratorLab.ts`)

| Method | Endpoint Expected | Purpose |
|--------|-------------------|---------|
| `listRuns()` | `GET /api/v1/executions` | List executions |
| `getRun(id)` | `GET /api/v1/executions/{id}` | Execution details |
| `createRun()` | `POST /api/v1/executions` | Create execution |
| `cancelRun(id)` | `POST /api/v1/executions/{id}/cancel` | Cancel execution |
| `retryRun(id)` | `POST /api/v1/executions/{id}/retry` | Retry execution |

---

## 2. Basic Backend API Routes

**Prefix**: Routes are mounted with `/v1` prefix.

| Endpoint | Method | Response Model | Description |
|----------|--------|----------------|-------------|
| `/health` | GET | `HealthResponse` | Basic health check |
| `/health/detailed` | GET | `HealthResponse` | Detailed with component checks |
| `/v1/capabilities` | GET | `CapabilitiesResponse` | Feature flags for tier detection |
| `/v1/pipelines` | GET | `ListPipelinesResponse` | List available pipelines |
| `/v1/pipelines/{name}` | GET | `PipelineDetailResponse` | Pipeline parameter schema |
| `/v1/pipelines/{name}/run` | POST | `ExecutionResponse` | Execute pipeline (sync) |
| `/v1/data/weeks` | GET | `QueryWeeksResponse` | Available weeks by tier |
| `/v1/data/symbols` | GET | `QuerySymbolsResponse` | Top symbols for week/tier |

### Key Response Shapes

```typescript
// GET /v1/capabilities
interface CapabilitiesResponse {
  api_version: string;     // "v1"
  tier: string;            // "basic" | "intermediate" | "full"
  version: string;         // semver package version
  sync_execution: boolean;
  async_execution: boolean;
  execution_history: boolean;
  authentication: boolean;
  scheduling: boolean;
  rate_limiting: boolean;
  webhook_notifications: boolean;
}

// GET /v1/pipelines
interface ListPipelinesResponse {
  pipelines: { name: string; description: string }[];
  count: number;
}

// GET /v1/pipelines/{name}
interface PipelineDetailResponse {
  name: string;
  description: string;
  required_params: ParameterDef[];
  optional_params: ParameterDef[];
  is_ingest: boolean;
}

// POST /v1/pipelines/{name}/run
interface ExecutionResponse {
  execution_id: string;
  pipeline: string;
  status: "completed" | "failed" | "dry_run";
  rows_processed: number | null;
  duration_seconds: number | null;
  poll_url: string | null;  // always null in Basic
}

// GET /v1/data/weeks?tier=OTC
interface QueryWeeksResponse {
  tier: string;
  weeks: { week_ending: string; symbol_count: number }[];
  count: number;
}

// GET /v1/data/symbols?tier=OTC&week=2025-12-29
interface QuerySymbolsResponse {
  tier: string;
  week: string;
  symbols: { symbol: string; volume: number; avg_price: number | null }[];
  count: number;
}
```

---

## 3. Mapping Table: UI Expects → Basic Provides → Action

| UI Expects | Basic Provides | Action |
|------------|----------------|--------|
| `POST /api/v1/query` (generic) | Not available | **Adapt client**: Remove generic query, use specific endpoints |
| `GET /api/v1/dashboard/health` | `GET /health` | **Adapt client**: Map paths, shape is compatible |
| `GET /api/v1/dashboard/pipelines` | `GET /v1/pipelines` | **Adapt client**: Map paths, adapt response shape |
| `GET /api/v1/dashboard/pipelines/{id}` | `GET /v1/pipelines/{name}` | **Adapt client**: Use name instead of id |
| `POST /api/v1/dashboard/pipelines/{id}/trigger` | `POST /v1/pipelines/{name}/run` | **Adapt client**: Map paths, adapt request/response |
| `GET /api/v1/dashboard/executions/*` | Not available (Basic has no history) | **Hide behind capability flag** |
| `GET /api/v1/dashboard/queues` | Not available | **Hide behind capability flag** |
| `GET /api/v1/dashboard/incidents` | Not available | **Hide behind capability flag** |
| `GET /api/v1/dashboard/failures` | Not available | **Hide behind capability flag** |
| `dataset: 'symbols'` | Not available | **Stub or hide** |
| `dataset: 'prices'` | Not available | **Stub or hide** |
| `dataset: 'otc_transparency'` | `GET /v1/data/symbols` (partial) | **Adapt client**: Map to data endpoints |
| `dataset: 'otc_top_volume'` | `GET /v1/data/symbols` + sort | **Adapt client**: Use data endpoints |
| `dataset: 'venues'` | Not available | **Stub or hide** |
| `dataset: 'liquidity'` | Not available | **Stub or hide** |
| Orchestrator Lab endpoints | Not available (Basic is sync only) | **Hide behind capability flag** |

---

## 4. Integration Strategy

### 4.1 Create New Spine Client (`src/api/spineClient.ts`)

A new unified client that:
- Reads `VITE_MARKET_SPINE_URL` for base URL
- Fetches `/v1/capabilities` on init
- Exposes typed methods for all Basic endpoints
- Normalizes errors to `{ code, message, details }`
- Provides feature flags for UI gating

### 4.2 Capabilities-Driven Feature Gating

```typescript
interface SpineCapabilities {
  tier: 'basic' | 'intermediate' | 'full';
  hasAsyncExecution: boolean;
  hasExecutionHistory: boolean;
  hasScheduling: boolean;
  hasQueues: boolean;
  hasIncidents: boolean;
  // ... derived from /v1/capabilities
}
```

React context (`SpineProvider`) exposes:
- `capabilities`: Current tier capabilities
- `isReady`: True when capabilities loaded
- `client`: The SpineClient instance

### 4.3 UI Adaptations

| Page/Widget | Adaptation |
|-------------|------------|
| OverviewPage | Show health + pipeline count; hide queues/incidents stats if unavailable |
| PipelinesPage | Use real pipelines list; simplify row (no schedule/success rate in Basic) |
| JobsPage | Hide or show empty state with "Requires Intermediate tier" message |
| QueuesPage | Hide or show upgrade message |
| IncidentsPage | Hide or show upgrade message |
| Orchestrator Lab | Hide or show upgrade message (no async execution) |
| OTC Widget | Map to `/v1/data/symbols` (limited to available data) |
| Price/Venue/Liquidity widgets | Show "Data source not configured" placeholder |

### 4.4 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_MARKET_SPINE_URL` | No | `''` (relative) | Backend base URL |
| `VITE_MARKET_SPINE_PROFILE` | No | `'auto'` | Force tier: `basic`, `intermediate`, `full`, or `auto` |
| `VITE_MOCK_MODE` | No | `'false'` | Use mock data for offline development |

---

## 5. Change Surface Map

Files to create:
- `src/api/spineClient.ts` — New unified API client
- `src/api/spineTypes.ts` — TypeScript types for Basic API
- `src/api/spineContext.tsx` — React context for capabilities
- `src/api/__tests__/spineClient.test.ts` — Client unit tests
- `.env.local.example` — Example environment file
- `docs/frontend-setup.md` — Setup documentation

Files to modify:
- `src/api/index.ts` — Re-export spine client
- `src/main.tsx` — Wrap with SpineProvider
- `src/dashboard/DashboardLayout.tsx` — Add health banner
- `src/dashboard/pages/OverviewPage.tsx` — Use real health/pipeline data
- `src/dashboard/pages/PipelinesPage.tsx` — Use spine client
- `src/dashboard/pages/JobsPage.tsx` — Add tier gate
- `src/dashboard/pages/QueuesPage.tsx` — Add tier gate
- `src/dashboard/pages/IncidentsPage.tsx` — Add tier gate
- `src/dashboard/pages/orchestrator/RecentRunsPage.tsx` — Add tier gate
- `src/widgets/OTCVolume/OTCVolume.tsx` — Adapt to available data
- `vite.config.ts` — Update proxy config
- `README.md` — Add frontend setup section

Files unchanged:
- `src/store/*` — State management unaffected
- `src/widgets/PriceChart/*` — Will show placeholder (no data source)
- `src/widgets/VenueScores/*` — Will show placeholder
- `src/widgets/Watchlist/*` — Local state only
- `src/widgets/TickerInput/*` — Local state only

---

## 6. Assumptions Made

1. **Basic is the primary target**: All adaptations prioritize working with Basic first.
2. **Sync-only execution**: Basic runs pipelines synchronously; no polling/status checking needed.
3. **No persistent execution history**: The ExecutionResponse is ephemeral; we display it but don't store.
4. **OTC data only**: Basic has FINRA OTC transparency data; prices/venues are not available.
5. **No authentication**: Basic tier has no auth; client doesn't send auth headers.
6. **Relative URLs work**: When `VITE_MARKET_SPINE_URL` is empty, vite proxy handles `/api/*` routes.
7. **Forward compatibility**: Client is designed to work with Intermediate/Full when they expose the same endpoints with additional features.
