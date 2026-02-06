# TODO: Frontend ↔ Backend Integration

> Created: 2026-01-04  
> Status: **ACTIVE**  
> Owner: Development Team

This document is the authoritative integration gameplan. It supersedes ad-hoc notes.

**Source Documents** (read these for context):
- [docs/frontend-api-contract.md](frontend-api-contract.md) — DTO definitions and client usage
- [docs/frontend-backend-integration-plan.md](frontend-backend-integration-plan.md) — Gap analysis and phase plan
- [docs/api/00-api-overview.md](api/00-api-overview.md) — API architecture and terminology
- [docs/api/02-basic-api-surface.md](api/02-basic-api-surface.md) — Basic tier endpoint specs
- [docs/api/03-intermediate-advanced-full-roadmap.md](api/03-intermediate-advanced-full-roadmap.md) — Tier evolution
- [docs/api/05-contract-clarifications-invariants.md](api/05-contract-clarifications-invariants.md) — Guarantees

---

## 0. Single Source of Truth

### Canonical API Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| **API Prefix** | `/v1` | All versioned endpoints under this prefix |
| **Health Endpoints** | `/health`, `/health/detailed` | No version prefix |
| **Frontend Env Var** | `VITE_MARKET_SPINE_URL` | Single canonical env var |
| **Legacy Env Var** | `VITE_API_URL` | **DEPRECATED** — do not use |

### Local Development Ports

| Service | Port | Notes |
|---------|------|-------|
| Basic API (docker) | `8010` | `docker-compose.yml` default |
| Basic API (local dev) | `8000` | `uvicorn` default |
| Frontend (docker prod) | `3110` | nginx static build |
| Frontend (docker dev) | `3111` | Vite hot reload |
| Frontend (local dev) | `5173` | `npm run dev` default |

### Environment Variable Setup

```bash
# .env for Trading Desktop
VITE_MARKET_SPINE_URL=http://localhost:8010
# OR for local dev without Docker:
VITE_MARKET_SPINE_URL=http://localhost:8000
```

---

## 0.1 Capture Semantics

### Default Behavior

All data endpoints return **latest capture** per logical partition:

```
GET /v1/data/symbols/{symbol}/history?tier=OTC&weeks=12
→ Returns latest capture_id for each (tier, week_ending, symbol)
```

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `capture_id` | string | latest | Specific capture (exact match) |
| `as_of` | timestamp | now | **Reserved** for point-in-time queries (future) |

### Capture Resolution Rules

1. **Default (no params)**: Latest `capture_id` per `(tier, week_ending)`
2. **With `capture_id`**: Exact match or 404
3. **With `as_of`**: Latest capture where `captured_at <= as_of` (not yet implemented)

### Response Metadata

All data responses include capture metadata:

```json
{
  "symbol": "AAPL",
  "tier": "NMS_TIER_1",
  "capture_id": "finra.otc:NMS_TIER_1:2025-12-22:20251223",
  "captured_at": "2025-12-23T08:15:00Z",
  "history": [...]
}
```

---

## 0.2 Pagination Conventions

### List Endpoints

All list endpoints support:

| Param | Type | Default | Max | Description |
|-------|------|---------|-----|-------------|
| `limit` | int | 10 | 100 | Items per page |
| `offset` | int | 0 | — | Skip N items |

### Response Shape

```json
{
  "items": [...],
  "count": 42,
  "limit": 10,
  "offset": 0,
  "has_more": true
}
```

### Server Caps

- **Hard limit**: 100 items per request (enforced server-side)
- **Soft limit**: 10 items default
- **Total count**: Included when `< 10000` rows; omitted for large tables

---

## 0.3 Frontend Resiliency

### Error Boundaries

Every widget and page must have an error boundary:

```tsx
// Required pattern
<WidgetErrorBoundary name="OTCVolume">
  <OTCVolume />
</WidgetErrorBoundary>
```

Error boundaries:
- Log errors to console (dev) or monitoring (prod)
- Show fallback UI with retry button
- Don't crash the entire app

### Capabilities-Aware Routing

**Never call endpoints not supported by the current tier.**

```tsx
// BAD - might 404 on Basic tier
const { data } = useQuery(['executions'], fetchExecutions);

// GOOD - check capabilities first
const { capabilities } = useSpine();
const { data } = useQuery(
  ['executions'],
  fetchExecutions,
  { enabled: capabilities?.hasExecutionHistory }
);
```

### Graceful Degradation Pattern

```tsx
function VenueScores() {
  const { tier, status } = useSpine();
  
  // Don't call endpoint if tier doesn't support it
  if (tier === 'basic') {
    return <TierUpgradeMessage feature="Venue Scores" requiredTier="advanced" />;
  }
  
  // Only fetch if tier supports it
  return <VenueScoresData />;
}
```

---

## 1. Current State

### What Works

| Component | Status | Notes |
|-----------|--------|-------|
| `/health`, `/v1/capabilities` | ✅ | Fully functional |
| `/v1/pipelines/*` | ✅ | List, describe, run all work |
| `/v1/data/weeks`, `/v1/data/symbols` | ✅ | Query works correctly |
| Dashboard Overview page | ✅ | Uses `spineClient` |
| Pipelines page | ✅ | Uses `spineClient` |
| Data Assets page | ✅ | Uses `spineClient` |
| Settings page | ✅ | Updated to use `spineClient`, shows tier |
| OTC Volume widget | ✅ | Updated to use `spineClient` |
| Price Chart widget | ✅ | Shows tier unavailable message |
| Venue Scores widget | ✅ | Shows tier unavailable message |

### What's Broken / Incomplete

| Component | Issue | Priority |
|-----------|-------|----------|
| `client.ts` legacy exports | Still exported from `api/index.ts` | P1 - Remove |
| `hooks.ts` legacy exports | Still exported from `api/index.ts` | P1 - Remove |
| OTC symbol history | No historical data endpoint | P2 - Add endpoint |
| Production frontend build | TypeScript strict mode may catch issues | P2 - Verify |
| Price data integration | No Alpha Vantage wiring | P3 - Phase 2 |
| Venue data integration | No external venue source | P4 - Phase 3+ |
| Execution history | Not in Basic tier | P3 - Intermediate |
| Storage/ops metrics | No `/v1/ops/*` endpoints | P3 - Intermediate |

### Files Still Using Legacy Client

**Immediate action required** — these exports must be removed:

| File | Legacy Usage | Action |
|------|--------------|--------|
| `trading-desktop/src/api/index.ts` | Exports `client.ts`, `hooks.ts` | Remove legacy exports |
| `trading-desktop/src/api/client.ts` | Uses `POST /api/v1/query` | Delete or archive |
| `trading-desktop/src/api/hooks.ts` | Depends on `client.ts` | Delete or archive |

**No widget files import legacy client** (verified via grep search) — the widget updates are complete.

---

## 2. Contract Map

### Frontend Components → Endpoints → Tier

| Page/Widget | Component | Endpoint | DTO | Tier | Status |
|-------------|-----------|----------|-----|------|--------|
| **Overview** | DashboardOverview | `GET /v1/pipelines` | `ListPipelinesResponse` | Basic | ✅ |
| | | `GET /v1/data/weeks?tier=OTC` | `QueryWeeksResponse` | Basic | ✅ |
| | | `GET /v1/capabilities` | `CapabilitiesResponse` | Basic | ✅ |
| **Pipelines** | PipelinesPage | `GET /v1/pipelines` | `ListPipelinesResponse` | Basic | ✅ |
| | PipelineDetail | `GET /v1/pipelines/{name}` | `PipelineDetail` | Basic | ✅ |
| | RunPipeline | `POST /v1/pipelines/{name}/run` | `ExecutionResponse` | Basic | ✅ |
| | ExecutionHistory | `GET /v1/executions` | `ExecutionListResponse` | Intermediate | 📋 Not yet |
| **Data Assets** | DataAssetsPage | `GET /v1/data/weeks` | `QueryWeeksResponse` | Basic | ✅ |
| | SymbolTable | `GET /v1/data/symbols` | `QuerySymbolsResponse` | Basic | ✅ |
| | ReadinessIndicator | `GET /v1/data/readiness` | `ReadinessResponse` | Intermediate | 📋 Not yet |
| | AnomalyList | `GET /v1/data/anomalies` | `AnomalyListResponse` | Intermediate | 📋 Not yet |
| **Settings** | SettingsPage | `GET /v1/capabilities` | `CapabilitiesResponse` | Basic | ✅ |
| | StorageStats | `GET /v1/ops/storage` | `StorageStatsResponse` | Basic+ | 📋 Proposed |
| | APIKeys | `/v1/auth/*` | Various | Full | 📋 Not yet |
| **Trading Desktop** | OTCVolume | `GET /v1/data/symbols` | `QuerySymbolsResponse` | Basic | ✅ |
| | OTCHistory | `GET /v1/data/symbols/{symbol}/history` | `SymbolHistoryResponse` | Basic | 📋 Proposed |
| | PriceChart | `GET /v1/data/prices/{symbol}` | `PriceDataResponse` | Intermediate+ | 📋 Not yet |
| | VenueScores | `GET /v1/data/venues/{symbol}` | `VenueScoreResponse` | Advanced | 📋 Not yet |
| | Watchlist | LocalStorage | N/A | Basic | ✅ (FE only) |

---

## 3. Phase Plan

### Phase 0: Hygiene (First 2 Hours)

**Goal**: Remove legacy cruft, ensure clean build, standardize on single client.

#### A. Frontend Tasks

- [x] **Remove legacy exports from `api/index.ts`** ✅ *2026-01-04*
  - File: `trading-desktop/src/api/index.ts`
  - Remove lines: `export * from './client'`, `export * from './hooks'`, `export { default as api }`
  - Keep: `spineClient`, `spineContext`, `spineTypes` exports

- [x] **Archive legacy files** ✅ *2026-01-04*
  - `trading-desktop/src/api/client.ts` → `trading-desktop/src/api/_archive/client.ts.bak`
  - `trading-desktop/src/api/hooks.ts` → `trading-desktop/src/api/_archive/hooks.ts.bak`

- [x] **Verify no remaining imports** ✅ *2026-01-04*
  ```powershell
  cd trading-desktop
  grep -r "from.*client" src/ --include="*.ts" --include="*.tsx" | grep -v spineClient
  grep -r "from.*hooks" src/ --include="*.ts" --include="*.tsx" | grep -v useTemporalContext
  ```

- [x] **Consolidate env vars** ✅ *2026-01-04*
  - File: `trading-desktop/.env.example`
  - Standardize on `VITE_MARKET_SPINE_URL` (remove `VITE_API_URL`)
  - Update `trading-desktop/src/api/spineClient.ts` to use single var

- [x] **Verify production build** ✅ *2026-01-04*
  ```powershell
  cd trading-desktop
  npm run build
  # Must exit 0 with no TypeScript errors
  ```

#### B. Backend Tasks

- [x] **Verify all Basic endpoints return documented shapes** ✅ *2026-01-04*
  - Tests in: `market-spine-basic/tests/test_api.py` (32 tests passing)
  - Covers: `/health`, `/v1/capabilities`, `/v1/pipelines`, `/v1/data/weeks`, `/v1/data/symbols`, `/v1/data/symbols/{symbol}/history`, `/v1/ops/storage`

#### C. Shared Contract Tasks

- [x] **Create OpenAPI spec for Basic tier** ✅ *2026-01-05*
  - FastAPI auto-generates at `GET /openapi.json`
  - Swagger UI available at `GET /docs`
  - ReDoc available at `GET /redoc`

**Definition of Done (Phase 0)**: ✅ COMPLETE
- [x] `npm run build` succeeds in `trading-desktop/`
- [x] No imports from `client.ts` or `hooks.ts`
- [x] All existing tests pass (32 API tests)
- [x] Docker dev build works: `docker compose --profile frontend-dev up` ✅ *2026-01-05*

---

### Phase 1: Basic Tier Complete

**Goal**: All pages work with zero console errors, graceful degradation, data loads correctly.

#### A. Frontend Tasks

- [x] **Add symbol history helper to spineClient** ✅ *2026-01-04*
  - File: `trading-desktop/src/api/spineClient.ts`
  - Method: `getSymbolHistory(symbol: string, tier: DataTier, weeks: number)`
  - Backend endpoint added: `GET /v1/data/symbols/{symbol}/history`
  - Types added: `SymbolWeekData`, `QuerySymbolHistoryResponse`

- [x] **Add ErrorBoundary components** ✅ *2026-01-04*
  - File: `trading-desktop/src/components/ErrorBoundary.tsx`
  - Components: `ErrorBoundary`, `WidgetErrorBoundary`

- [x] **Enhance OTC Volume widget with symbol detail panel** ✅ *2026-01-05*
  - File: `trading-desktop/src/widgets/OTCVolume/OTCVolume.tsx`
  - When symbol selected, show:
    - Latest week data (already done)
    - "View history" button (links to Data Assets page with symbol filter)
    - Clear message: "Multi-week history requires Intermediate tier"
  - Added symbol history panel to DataAssetsPage with URL params support

- [x] **Add empty state improvements** ✅ *2026-01-05*
  - Created: `trading-desktop/src/components/EmptyState.tsx`
  - Components: `EmptyState`, `NoDataEmptyState`, `ConnectionErrorEmptyState`
  - Integrated into `DataAssetsPage.tsx`

- [x] **Add loading skeletons** ✅ *2026-01-05*
  - Created: `trading-desktop/src/components/Skeleton.tsx`
  - Components: `Skeleton`, `SkeletonText`, `SkeletonTable`, `SkeletonWidget`
  - Integrated into `DataAssetsPage.tsx`, `OTCVolume.tsx`

- [x] **Verify mobile/responsive layout** ✅ *2026-01-05*
  - Trading Desktop: FlexLayout is inherently responsive
  - Dashboard: Added CSS for data-grid stacking on < 1200px, smaller data-table cells on mobile
  - Added tier-tabs wrapping on small screens

#### B. Backend Tasks

- [x] **Add symbol history endpoint** ✅ *2026-01-04*
  - File: `market-spine-basic/src/market_spine/api/routes/v1/pipelines.py`
  - Endpoint: `GET /v1/data/symbols/{symbol}/history`
  - Query params: `tier`, `weeks` (default: 12, max: 52)
  - Command: `QuerySymbolHistoryCommand` in `queries.py`
  - Tests: 5 tests in `test_api.py::TestSymbolHistoryEndpoint`

- [x] **Add storage stats endpoint** ✅ *2026-01-04*
  - File: `market-spine-basic/src/market_spine/api/routes/v1/ops.py`
  - Endpoint: `GET /v1/ops/storage`
  - Response includes: `database_path`, `database_size_bytes`, `tables[]`, `total_rows`
  - Tests: 2 tests in `test_api.py::TestOpsStorageEndpoint`

- [x] **Add capture list endpoint** ✅ *2026-01-05*
  - Endpoint: `GET /v1/ops/captures`
  - Response: List of capture IDs with tier, week_ending, captured_at, row counts
  - File: `market-spine-basic/src/market_spine/api/routes/v1/ops.py`
  - Frontend types: `CaptureInfo`, `CapturesListResponse`
  - Client method: `listCaptures()`

#### C. Shared Contract Tasks

- [x] **Add DTO types for new endpoints** ✅ *2026-01-04*
  - File: `trading-desktop/src/api/spineTypes.ts`
  - Added: `SymbolWeekData`, `QuerySymbolHistoryResponse`, `TableStats`, `StorageStatsResponse`
  - Client methods: `getSymbolHistory()`, `getStorageStats()`

- [x] **Document new endpoints in API spec** ✅ *2026-01-05*
  - Updated: `docs/api/02-basic-api-surface.md` to v1.1
  - Added: `/v1/data/symbols/{symbol}/history`, `/v1/ops/storage`, `/v1/ops/captures`
  - Updated Route Overview and Control Plane tables

**Definition of Done (Phase 1)**: ✅ COMPLETE *2026-01-05*
- [x] All dashboard pages load without 4xx/5xx errors
- [x] Console shows no errors on page navigation
- [x] OTC widget displays top symbols correctly
- [x] Settings shows API version and tier from `/v1/capabilities`
- [x] Empty database shows helpful empty states (not broken UI)
- [x] Run demo walkthrough successfully (see Demo Instructions below)

---

### Phase 1.5: Dashboard Enhancements ✅ COMPLETE *2026-01-05*

**Goal**: Use new ops endpoints to enhance dashboard visibility.

#### A. Frontend Tasks

- [x] **Add storage stats to Overview page** ✅ *2026-01-05*
  - File: `trading-desktop/src/dashboard/pages/OverviewPage.tsx`
  - Added Database Size stat card using `/v1/ops/storage`
  - Shows formatted bytes (KB/MB/GB)

- [x] **Add storage stats to Settings page** ✅ *2026-01-05*
  - File: `trading-desktop/src/dashboard/pages/SettingsPage.tsx`
  - New "Storage Statistics" section with DB size, total rows, table breakdown
  - Shows top 5 tables with row counts

- [x] **Add captures list to Settings page** ✅ *2026-01-05*
  - File: `trading-desktop/src/dashboard/pages/SettingsPage.tsx`
  - New "Data Captures" section using `/v1/ops/captures`
  - Shows recent captures with week, tier, and row counts
  - Helpful for debugging data lineage

**Definition of Done (Phase 1.5)**: ✅ COMPLETE
- [x] Overview page shows Database Size stat
- [x] Settings page shows storage statistics with table breakdown
- [x] Settings page shows data captures list
- [x] Build succeeds: `npm run build`

---

### Phase 1.6: Overview Page Design Alignment ✅ COMPLETE *2026-01-04*

**Goal**: Align Overview page with dashboard-design spec (04-page-global-overview.md).

#### A. Frontend Tasks

- [x] **Add Data Freshness Card** ✅ *2026-01-04*
  - File: `trading-desktop/src/dashboard/pages/OverviewPage.tsx`
  - Shows all 3 tiers: OTC, NMS Tier 1, NMS Tier 2
  - Visual indicators: ✓ (fresh), ⚠ (warning: 7-14 days), ⚠️ (stale: >14 days)
  - Empty state when no data ingested

- [x] **Improve Health Summary Logic** ✅ *2026-01-04*
  - Derive overall status from: backend health, data freshness
  - Three states: healthy (green), warning (yellow), degraded (red)
  - Show status reason text for non-healthy states
  - Warning for stale data or no data conditions

- [x] **Add CSS for new components** ✅ *2026-01-04*
  - File: `trading-desktop/src/index.css`
  - `.data-freshness-card`, `.freshness-grid`, `.freshness-row`
  - `.status-warning` banner style
  - `.icon-warning`, `.status-hint` styles

**Definition of Done (Phase 1.6)**: ✅ COMPLETE
- [x] Data Freshness Card shows all tiers with staleness indicators
- [x] Status banner shows warning state for stale/no data
- [x] Build succeeds: `npm run build`
- [x] API tests pass: 34/34

---

### Phase 2: External Data Sources (Prices)

**Goal**: Add Alpha Vantage integration for price charts.

#### A. Frontend Tasks

- [ ] **Enable PriceChart widget for Intermediate+ tier**
  - File: `trading-desktop/src/widgets/PriceChart/PriceChart.tsx`
  - Check `tier === 'intermediate' || tier === 'advanced' || tier === 'full'`
  - Fetch from `/v1/data/prices/{symbol}?days=30`
  - Render candlestick chart with Lightweight Charts

- [ ] **Add price data types**
  - File: `trading-desktop/src/api/spineTypes.ts`
  - Add: `PriceCandle`, `PriceDataResponse`

- [ ] **Add price query method to spineClient**
  - Method: `getPrices(symbol: string, days: number)`

#### B. Backend Tasks

- [ ] **Create market_data domain**
  - New package: `packages/spine-domains/src/spine_domains/market_data/`
  - Module: `prices.py` with Alpha Vantage adapter

- [ ] **Add Alpha Vantage source adapter**
  - File: `market-spine-intermediate/src/.../sources/alpha_vantage.py`
  - Handle API key from env var: `ALPHA_VANTAGE_API_KEY`
  - Rate limiting: 5 requests/minute for free tier

- [ ] **Add price ingestion pipeline**
  - Pipeline: `market_data.prices.fetch_daily`
  - Params: `symbol`, `outputsize` (compact/full)

- [ ] **Add price query endpoints**
  - `GET /v1/data/prices/{symbol}?days=30` — Daily OHLCV
  - `GET /v1/data/prices/{symbol}/latest` — Latest quote

- [ ] **Add price data tables**
  ```sql
  CREATE TABLE market_data_prices_raw (
    capture_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    date DATE NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date, capture_id)
  );
  ```

#### C. Shared Contract Tasks

- [ ] **Add price endpoints to OpenAPI**
- [ ] **Add price types to frontend-api-contract.md**

**Definition of Done (Phase 2)**:
- [ ] Price chart renders for any symbol with available data
- [ ] Alpha Vantage API key configurable via env
- [ ] Rate limiting prevents API quota exhaustion
- [ ] Graceful fallback when no price data available

---

### Phase 3: Intermediate Tier Ops Dashboards

**Goal**: Execution history, queue visibility, data readiness indicators.

#### A. Frontend Tasks

- [ ] **Add Executions page** (`/dashboard/executions`)
  - List recent executions with status, duration, rows processed
  - Filter by pipeline, status, date range
  - Click to view execution details

- [ ] **Add execution detail view**
  - Show parameters, events timeline, output logs
  - Retry/cancel buttons for failed/running executions

- [ ] **Add Queue visibility widget** (Flower-style)
  - Show worker status, queue depths, processing rate
  - Real-time updates via polling

- [ ] **Add Data Readiness indicators**
  - On Data Assets page, show readiness badge per week
  - Color: green (ready), yellow (processing), red (failed)

- [ ] **Add Anomaly list**
  - On Data Assets page, show quality issues
  - Severity badges: CRITICAL (red), ERROR (orange), WARN (yellow)

#### B. Backend Tasks

- [ ] **Add execution endpoints** (Intermediate tier)
  - `GET /v1/executions` — List with filters
  - `GET /v1/executions/{id}` — Detail
  - `GET /v1/executions/{id}/events` — Event log
  - `POST /v1/executions/{id}/cancel` — Cancel running

- [ ] **Add queue endpoints**
  - `GET /v1/queues` — Queue status
  - `GET /v1/workers` — Worker status

- [ ] **Add readiness endpoint**
  - `GET /v1/data/readiness?tier=...&week=...`
  - Response: `{ is_ready, ready_for, raw_complete, normalized_complete, ... }`

- [ ] **Add anomalies endpoint**
  - `GET /v1/data/anomalies?tier=...&week=...&severity=...`
  - Response: List of anomaly objects

#### C. Shared Contract Tasks

- [ ] **Define execution DTOs**
- [ ] **Define queue/worker DTOs**
- [ ] **Define readiness/anomaly DTOs**

**Definition of Done (Phase 3)**:
- [ ] Executions page shows history with correct status
- [ ] Can cancel a running execution
- [ ] Queue widget shows accurate depths
- [ ] Readiness badges appear on Data Assets
- [ ] Anomalies display with severity levels

---

## 4. Dashboard Inspirations

### Airflow-Style Runs View

**Inspiration**: Apache Airflow DAG runs grid  
**Adapted for Spine**:
- Pipeline list on left
- Grid of execution statuses (green/red/yellow squares)
- Click to drill into execution details
- Filter by date range, status

**Implementation Notes**:
- Use TanStack Table for the grid
- Polling every 5s for status updates
- Cache execution history in React Query

### Flower-Style Worker View

**Inspiration**: Celery Flower dashboard  
**Adapted for Spine**:
- Worker cards showing hostname, status, current task
- Queue depth charts (line chart over time)
- Task rate chart (tasks/minute)

**Implementation Notes**:
- Only visible in Advanced+ tier
- Pull from `/v1/workers` and `/v1/queues`
- Use Recharts for simple charts

### Grafana-Style Metrics Panels

**Inspiration**: Grafana dashboard panels  
**Adapted for Spine**:
- Database size over time
- Rows ingested per day
- Execution duration trends
- Error rate trends

**Implementation Notes**:
- Requires metrics storage (Phase 3+)
- Consider using Prometheus for metrics collection
- Frontend fetches from `/v1/ops/metrics?range=7d`

---

## 5. Metrics Over Time Plan

### Tables to Track

| Metric | Table/Source | Frequency |
|--------|--------------|-----------|
| Database size | SQLite `PRAGMA database_size` or pg stats | Daily |
| Row counts per table | `COUNT(*)` per table | Daily |
| Queue depth snapshots | Celery/Redis inspection | Every 1 min |
| Execution durations | `executions` table | Per execution |
| Error counts | `executions` where status='failed' | Per execution |
| Capture counts | `manifests` table | Per capture |

### Metrics Storage

**Option A: In-database metrics table** (Basic/Intermediate)
```sql
CREATE TABLE spine_metrics (
  metric_name TEXT NOT NULL,
  metric_value REAL NOT NULL,
  labels JSONB,
  recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_metrics_name_time ON spine_metrics(metric_name, recorded_at);
```

**Option B: Prometheus** (Advanced/Full)
- Expose `/metrics` endpoint with Prometheus format
- Scrape with Prometheus server
- Query via PromQL from Grafana or custom UI

### Endpoints

| Endpoint | Description | Tier |
|----------|-------------|------|
| `GET /v1/ops/storage` | Current db size, row counts, top tables | Basic |
| `GET /v1/ops/retention/plan?older_than_days=90` | Preview what would be deleted | Intermediate |
| `POST /v1/ops/retention/run?older_than_days=90&dry_run=1` | Execute retention (or dry-run) | Intermediate |
| `GET /v1/ops/metrics?range=7d&metric=db_size` | Time series metrics | Intermediate |
| `GET /metrics` | Prometheus scrape endpoint | Advanced |

### Retention Management (Intermediate+)

#### GET /v1/ops/retention/plan

Preview data eligible for deletion:

```json
{
  "older_than_days": 90,
  "preview_at": "2026-01-04T12:00:00Z",
  "affected_tables": {
    "finra_otc_transparency_raw": {
      "rows_to_delete": 45000,
      "oldest_capture": "2025-09-15",
      "newest_affected": "2025-10-05"
    },
    "finra_otc_transparency_normalized": {
      "rows_to_delete": 45000,
      "oldest_capture": "2025-09-15", 
      "newest_affected": "2025-10-05"
    }
  },
  "total_rows_affected": 90000,
  "estimated_space_bytes": 15728640
}
```

#### POST /v1/ops/retention/run

Execute retention with safety defaults:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `older_than_days` | int | **required** | Must be >= 30 |
| `dry_run` | bool | `true` | **Default safe** - set to `false` to actually delete |
| `confirm` | string | — | Must equal `"DELETE"` when `dry_run=false` |

Response:

```json
{
  "dry_run": false,
  "deleted_rows": 90000,
  "affected_tables": ["finra_otc_transparency_raw", "finra_otc_transparency_normalized"],
  "space_reclaimed_bytes": 15728640,
  "execution_time_seconds": 2.5
}
```

**Safety guarantees:**
- `dry_run=true` by default (never destructive without explicit opt-in)
- `older_than_days` minimum is 30 (cannot delete recent data)
- `confirm="DELETE"` required for actual deletion
- Audit log entry created for every retention run

### Frontend Graphs

| Graph | Data Source | Library |
|-------|-------------|---------|
| Database size (sparkline) | `/v1/ops/storage` | Recharts AreaChart |
| Rows ingested/day | `/v1/ops/metrics?metric=rows_ingested` | Recharts BarChart |
| Execution duration (histogram) | `/v1/executions` | Recharts BarChart |
| Queue depth (line) | `/v1/queues` | Recharts LineChart |

---

## 6. Acceptance Criteria & Test Plan

### Phase 0 Acceptance

| Test | Command/Action | Expected |
|------|----------------|----------|
| Build succeeds | `cd trading-desktop && npm run build` | Exit code 0, no TS errors |
| No legacy imports | `grep -r "from.*client" src/` | No matches (except spineClient) |
| Dev server works | `docker compose --profile frontend-dev up` | Vite starts, no errors |
| API health | `curl http://localhost:8010/health` | `{"status": "healthy"}` |

### Phase 1 Acceptance

| Test | Page/Widget | Expected Behavior |
|------|-------------|-------------------|
| Overview loads | `/dashboard` | Pipeline count, week count displayed |
| Pipelines list | `/dashboard/pipelines` | All pipelines shown |
| Run pipeline | Click Run → fill params → submit | Execution completes, toast shows |
| Data Assets | `/dashboard/data-assets` | Weeks list, click to see symbols |
| OTC widget | Trading Desktop | Top symbols displayed |
| Symbol click | OTC widget → click row | Symbol selected, detail shown |
| Settings | `/dashboard/settings` | API version, tier, connection status |
| Empty state | Clear database, reload | "No data" message with CTA |

### Phase 2 Acceptance

| Test | Expected |
|------|----------|
| Price chart renders | Select symbol with price data → chart appears |
| No price fallback | Symbol without price data → "No price data" message |
| API rate limiting | Rapid requests → queued, not dropped |

### Phase 3 Acceptance

| Test | Expected |
|------|----------|
| Executions page | Lists recent executions with correct status |
| Execution detail | Shows params, events, duration |
| Queue widget | Shows worker count, queue depth |
| Readiness badge | Green/yellow/red on Data Assets |
| Anomalies display | List with severity colors |

---

## 7. First 2 Hours (Quick Wins)

Do these first for immediate impact:

1. **Remove legacy exports** (5 min)
   - Edit `trading-desktop/src/api/index.ts`
   - Remove `client.ts` and `hooks.ts` exports

2. **Verify production build** (5 min)
   - `cd trading-desktop && npm run build`
   - Fix any TS errors

3. **Update `.env.example`** (2 min)
   - Standardize on `VITE_MARKET_SPINE_URL`

4. **Add empty state to Overview** (15 min)
   - When pipelines = 0 or weeks = 0, show helpful message

5. **Add storage stats endpoint** (30 min)
   - Simple endpoint to show db size in Settings

6. **Run full demo walkthrough** (15 min)
   - Document any issues found

7. **Write API contract test** (30 min)
   - Verify `/v1/capabilities` response shape
   - Verify `/v1/pipelines` response shape

---

## 8. Risk List & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **CORS issues** | Medium | High | Backend already has CORS middleware; verify `allow_origins` config |
| **Proxy misconfiguration** | Medium | High | Test nginx config with curl before trusting browser |
| **Contract drift** | High | Medium | Add contract tests that run in CI; fail build on mismatch |
| **Missing fields in response** | Medium | Low | Use TypeScript optional chaining; add defaults in client |
| **Alpha Vantage rate limits** | High | Medium | Implement request queue with backoff; cache aggressively |
| **Large result sets** | Medium | Medium | Always use pagination; set reasonable defaults (limit=100) |
| **WebSocket not in Basic** | Low | Low | Use polling for now; document in capabilities |
| **Stale React Query cache** | Medium | Low | Use proper query keys; invalidate on mutations |
| **Docker volume permissions** | Medium | Medium | Use named volumes; verify uid/gid in Dockerfile |

### CORS Configuration Checklist

```python
# market-spine-basic/src/market_spine/api/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3100", "http://localhost:3111"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Contract Test Example

```python
# market-spine-basic/tests/test_api_contracts.py
def test_capabilities_response_shape(client):
    response = client.get("/v1/capabilities")
    assert response.status_code == 200
    data = response.json()
    
    # Required fields
    assert "api_version" in data
    assert "tier" in data
    assert data["tier"] in ["basic", "intermediate", "full"]
    assert "sync_execution" in data
    assert isinstance(data["sync_execution"], bool)
```

---

## 9. Demo Instructions

### Quick Demo (5 minutes)

```powershell
# 1. Start containers
cd c:\projects\spine-core\market-spine-basic
docker compose --profile frontend-dev up -d

# 2. Ingest sample data
Invoke-RestMethod -Method POST "http://localhost:8010/v1/pipelines/finra.otc_transparency.ingest_week/run" `
  -ContentType "application/json" `
  -Body '{"params": {"week_ending": "2025-12-22", "tier": "OTC", "file": "data/finra/finra_otc_weekly_otc_20251222.csv"}}'

# 3. Open frontend
Start-Process "http://localhost:3111"
```

### Walkthrough

1. **Dashboard Overview** → Verify pipeline count, week count
2. **Pipelines** → Click any pipeline → Verify details load
3. **Data Assets** → Select OTC tab → Click week → Verify symbols
4. **Trading Desktop** → OTC widget → Click symbol → Verify selection
5. **Settings** → Verify API version shows, tier shows "basic"

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Connecting to Market Spine..." forever | Wrong API URL | Check `VITE_MARKET_SPINE_URL` |
| 404 on API calls | Missing `/v1` prefix | Check spineClient base URL |
| CORS error | Missing origin in allow list | Add origin to CORS config |
| Empty OTC widget | No data ingested | Run ingest pipeline |
| TypeScript errors on build | Type mismatch | Check spineTypes.ts definitions |

---

## Appendix A: File Reference

### Frontend Files (to modify)

| File | Purpose | Phase |
|------|---------|-------|
| `trading-desktop/src/api/index.ts` | Remove legacy exports | 0 |
| `trading-desktop/src/api/spineClient.ts` | Add helper methods | 1 |
| `trading-desktop/src/api/spineTypes.ts` | Add new DTOs | 1, 2, 3 |
| `trading-desktop/src/widgets/OTCVolume/OTCVolume.tsx` | Enhance symbol detail | 1 |
| `trading-desktop/src/widgets/PriceChart/PriceChart.tsx` | Enable for Intermediate | 2 |
| `trading-desktop/src/dashboard/pages/SettingsPage.tsx` | Add storage stats | 1 |
| `trading-desktop/src/dashboard/pages/ExecutionsPage.tsx` | New page | 3 |

### Backend Files (to modify/create)

| File | Purpose | Phase |
|------|---------|-------|
| `market-spine-basic/src/market_spine/api/routes/data.py` | Add symbol history | 1 |
| `market-spine-basic/src/market_spine/api/routes/ops.py` | Add storage stats | 1 |
| `market-spine-intermediate/src/.../routes/executions.py` | Execution endpoints | 3 |
| `market-spine-intermediate/src/.../routes/queues.py` | Queue endpoints | 3 |
| `packages/spine-domains/src/spine_domains/market_data/` | Price domain | 2 |

### Test Files (to create)

| File | Purpose |
|------|---------|
| `market-spine-basic/tests/test_api_contracts.py` | Contract tests |
| `trading-desktop/src/api/__tests__/spineClient.test.ts` | Client unit tests |
| `trading-desktop/e2e/basic-tier.spec.ts` | E2E tests for Basic |

---

## Appendix B: Proposed DTOs

### SymbolHistoryResponse (Phase 1)

```typescript
interface SymbolHistoryEntry {
  week_ending: string;
  volume: number;
  rank: number;
  wow_change: number | null;
}

interface SymbolHistoryResponse {
  symbol: string;
  tier: DataTier;
  history: SymbolHistoryEntry[];
  count: number;
}
```

### StorageStatsResponse (Phase 1)

```typescript
interface StorageStatsResponse {
  database_size_bytes: number;
  row_counts: Record<string, number>;
  oldest_capture: string | null;
  newest_capture: string | null;
}
```

### ExecutionListResponse (Phase 3)

```typescript
interface ExecutionSummary {
  execution_id: string;
  pipeline: string;
  status: 'completed' | 'failed' | 'running' | 'pending' | 'cancelled';
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  rows_processed: number | null;
}

interface ExecutionListResponse {
  executions: ExecutionSummary[];
  count: number;
  has_more: boolean;
}
```

### QueueStatusResponse (Phase 3)

```typescript
interface QueueStatus {
  name: string;
  depth: number;
  consumers: number;
  messages_per_second: number;
}

interface WorkerStatus {
  hostname: string;
  status: 'online' | 'offline' | 'busy';
  current_task: string | null;
  tasks_completed: number;
}

interface QueueStatusResponse {
  queues: QueueStatus[];
  workers: WorkerStatus[];
  total_pending: number;
  total_workers: number;
}
```
