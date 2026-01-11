# Frontend API Contract

> Last Updated: 2026-01-04  
> Version: 1.0  
> Status: **AUTHORITATIVE**

This document defines the frontend's normalized DTOs and how they map to backend API responses.

---

## 1. Client Architecture

The frontend uses a **unified SpineClient** for all backend communication:

```typescript
// Primary client - use this everywhere
import { spineClient, useSpineClient, useSpine } from '@/api';

// Context provides client + capabilities + health
const { client, capabilities, status, tier, health } = useSpine();
```

### Client Configuration

```typescript
interface SpineClientConfig {
  baseUrl?: string;     // Default: '' (relative to origin)
  timeout?: number;     // Default: 30000ms
  enableTracing?: boolean;  // Default: true
}
```

### Error Handling

All errors are thrown as `SpineError`:

```typescript
class SpineError extends Error {
  code: string;           // Machine-readable code
  message: string;        // Human-readable message
  details?: Record<string, unknown>;
  httpStatus?: number;
}
```

---

## 2. Health & Capabilities DTOs

### HealthResponse

```typescript
interface HealthResponse {
  status: 'ok' | 'error' | 'warning';
  timestamp: string;  // ISO 8601
  checks?: ComponentHealth[];
  details?: Record<string, unknown>;
}

interface ComponentHealth {
  name: string;
  status: 'ok' | 'error' | 'warning';
  message: string;
  latency_ms?: number;
}
```

**Backend Endpoint**: `GET /health`, `GET /health/detailed`

### CapabilitiesResponse

```typescript
interface CapabilitiesResponse {
  api_version: string;        // "v1"
  tier: 'basic' | 'intermediate' | 'full';
  version: string;            // "0.5.0"
  sync_execution: boolean;
  async_execution: boolean;
  execution_history: boolean;
  authentication: boolean;
  scheduling: boolean;
  rate_limiting: boolean;
  webhook_notifications: boolean;
}

// Derived capabilities for UI feature gating
interface SpineCapabilities extends CapabilitiesResponse {
  hasAsyncExecution: boolean;
  hasExecutionHistory: boolean;
  hasScheduling: boolean;
  hasQueues: boolean;
  hasIncidents: boolean;
  hasOrchestratorLab: boolean;
  hasDataLineage: boolean;
}
```

**Backend Endpoint**: `GET /v1/capabilities`

---

## 3. Pipeline DTOs

### ListPipelinesResponse

```typescript
interface PipelineSummary {
  name: string;         // "finra.otc_transparency.ingest_week"
  description: string;  // "Ingest FINRA OTC weekly data"
}

interface ListPipelinesResponse {
  pipelines: PipelineSummary[];
  count: number;
}
```

**Backend Endpoint**: `GET /v1/pipelines`

### PipelineDetail

```typescript
interface ParameterDef {
  name: string;
  type: string;           // "string", "date", "int", "path"
  description: string;
  default?: unknown;
  required: boolean;
  choices?: string[];
}

interface PipelineDetail {
  name: string;
  description: string;
  required_params: ParameterDef[];
  optional_params: ParameterDef[];
  is_ingest: boolean;
}
```

**Backend Endpoint**: `GET /v1/pipelines/{name}`

### ExecutionResponse

```typescript
interface ExecutionResponse {
  execution_id: string;       // UUID
  pipeline: string;           // Pipeline name
  status: 'completed' | 'failed' | 'dry_run' | 'pending' | 'running';
  rows_processed: number | null;
  duration_seconds: number | null;
  poll_url: string | null;    // Always null in Basic tier
}
```

**Backend Endpoint**: `POST /v1/pipelines/{name}/run`

---

## 4. Data Query DTOs

### DataTier

```typescript
type DataTier = 'OTC' | 'NMS_TIER_1' | 'NMS_TIER_2';
```

### QueryWeeksResponse

```typescript
interface WeekInfo {
  week_ending: string;    // "2025-12-22" (YYYY-MM-DD)
  symbol_count: number;
}

interface QueryWeeksResponse {
  tier: DataTier;
  weeks: WeekInfo[];
  count: number;
}
```

**Backend Endpoint**: `GET /v1/data/weeks?tier={tier}&limit={limit}`

### QuerySymbolsResponse

```typescript
interface SymbolInfo {
  symbol: string;         // "AAPL"
  volume: number;         // Total share volume
  avg_price: number | null;
}

interface QuerySymbolsResponse {
  tier: DataTier;
  week: string;           // "2025-12-22"
  symbols: SymbolInfo[];
  count: number;
}
```

**Backend Endpoint**: `GET /v1/data/symbols?tier={tier}&week={week}&top={top}`

---

## 5. OTC Data DTOs (Trading Desktop)

### OTCWeeklyData

Frontend normalized DTO for OTC volume widget:

```typescript
interface OTCWeeklyData {
  week_ending: string;      // "2025-12-22"
  symbol: string;
  total_volume: number;     // Total shares traded
  trade_count: number;      // Number of trades
  rank: number;             // Volume rank (1 = highest)
  // Computed fields (may be null if insufficient data)
  wow_change: number | null;   // Week-over-week % change
  avg_volume_6w: number | null; // Rolling 6-week average
}
```

**Mapping from Backend**:

```typescript
// Map from QuerySymbolsResponse to OTCWeeklyData
function mapToOTCData(symbol: SymbolInfo, rank: number, week: string): OTCWeeklyData {
  return {
    week_ending: week,
    symbol: symbol.symbol,
    total_volume: symbol.volume,
    trade_count: 0,          // Not available in basic response
    rank: rank,
    wow_change: null,        // Requires historical data
    avg_volume_6w: null,     // Requires historical data
  };
}
```

---

## 6. Placeholder DTOs (Not Available in Basic)

### PriceData (Phase 2)

```typescript
interface PriceCandle {
  time: string;           // "2025-12-22" or ISO timestamp
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface PriceDataResponse {
  symbol: string;
  interval: 'daily' | '1h' | '15m' | '5m' | '1m';
  candles: PriceCandle[];
  source: string;         // "alpha_vantage", "polygon", etc.
}
```

**Status**: Not implemented in Basic tier. Price chart shows unavailable message.

### VenueScore (Phase 2+)

```typescript
interface VenueScore {
  venue: string;          // "NSDQ", "ARCX", etc.
  symbol: string;
  fill_rate: number;      // 0.0 - 1.0
  slippage_bps: number;   // Basis points
  latency_ms: number;
  volume: number;
  score: number;          // Composite score 0.0 - 1.0
  updated_at: string;     // ISO timestamp
}
```

**Status**: Not implemented in Basic tier. Venue widget shows unavailable message.

---

## 7. Feature Gating

### Capability-Based Rendering

```tsx
import { FeatureGate, TierUpgradeMessage } from '@/api';

// Hide feature if not available
<FeatureGate feature="hasScheduling">
  <ScheduleBuilder />
</FeatureGate>

// Show upgrade message as fallback
<FeatureGate 
  feature="hasExecutionHistory" 
  fallback={<TierUpgradeMessage feature="Execution History" requiredTier="intermediate" />}
>
  <ExecutionHistoryTable />
</FeatureGate>
```

### Tier-Based Logic

```typescript
const { tier, capabilities } = useSpine();

// Check tier directly
if (tier === 'basic') {
  return <BasicDashboard />;
}

// Check specific capability
if (capabilities?.hasAsyncExecution) {
  showAsyncOptions();
}
```

---

## 8. Request Options

All client methods accept optional `RequestOptions`:

```typescript
interface RequestOptions {
  signal?: AbortSignal;       // For cancellation
  requestId?: string;         // Override generated ID
  headers?: Record<string, string>;  // Additional headers
}

// Usage
const controller = new AbortController();
const result = await client.listPipelines(undefined, { signal: controller.signal });

// Cancel on unmount
useEffect(() => {
  return () => controller.abort();
}, []);
```

---

## 9. Query Key Conventions

For React Query cache management:

```typescript
const queryKeys = {
  // Spine health/capabilities
  health: ['spine', 'health'],
  capabilities: ['spine', 'capabilities'],
  
  // Pipelines
  pipelines: ['spine', 'pipelines'],
  pipelineDetail: (name: string) => ['spine', 'pipeline', name],
  
  // Data queries
  weeks: (tier: DataTier) => ['spine', 'data', 'weeks', tier],
  symbols: (tier: DataTier, week: string) => ['spine', 'data', 'symbols', tier, week],
  
  // Trading data (when available)
  prices: (symbol: string) => ['spine', 'prices', symbol],
  otcHistory: (symbol: string) => ['spine', 'otc', symbol],
  venues: (symbol: string) => ['spine', 'venues', symbol],
};
```

---

## 10. Error Codes

| Code | HTTP | Description | Frontend Action |
|------|------|-------------|-----------------|
| `NETWORK_ERROR` | — | Cannot connect to backend | Show connection error |
| `REQUEST_TIMEOUT` | — | Request timed out | Show retry option |
| `PIPELINE_NOT_FOUND` | 404 | Pipeline doesn't exist | Show not found |
| `INVALID_TIER` | 400 | Invalid tier parameter | Show validation error |
| `INVALID_DATE` | 400 | Invalid date format | Show validation error |
| `INVALID_PARAMS` | 400 | Missing/invalid params | Highlight form fields |
| `DATA_NOT_READY` | 409 | Data not ready yet | Show pending state |
| `INTERNAL_ERROR` | 500 | Server error | Show error + retry |

---

## 11. Migration Guide (Legacy Client)

### Before (Legacy client.ts)

```typescript
// DON'T USE - endpoint doesn't exist
import api from './client';
const otcData = await api.getOTCData('AAPL', 12);
```

### After (SpineClient)

```typescript
// USE THIS
import { spineClient } from './spineClient';

// For top symbols (works now)
const topSymbols = await spineClient.querySymbols('NMS_TIER_1', '2025-12-22', 10);

// For price data (not available in Basic)
// Show unavailable message instead
```

### Hook Migration

```typescript
// Before (hooks.ts - legacy)
const { data } = useOTCData(symbol);

// After (inline with spineClient)
const { data } = useQuery({
  queryKey: ['spine', 'data', 'symbols', tier, week],
  queryFn: () => spineClient.querySymbols(tier, week, 50),
});
```
