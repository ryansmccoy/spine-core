# Frontend ↔ Backend Integration Plan

> Last Updated: 2026-01-04  
> Version: 1.0  
> Status: **IMPLEMENTATION PLAN**

This document maps the frontend (`trading-desktop`) data requirements to the backend API, identifies gaps, and defines the work needed for full Basic tier integration.

---

## 1. Executive Summary

### Current State
- **Frontend**: Two API clients exist:
  - `client.ts` (legacy) - uses `/api/v1/query` POST endpoint (doesn't exist in Basic backend)
  - `spineClient.ts` (new) - uses proper REST endpoints (`/v1/pipelines`, `/v1/data/*`)
- **Backend**: Basic tier has `/health`, `/v1/capabilities`, `/v1/pipelines/*`, `/v1/data/weeks`, `/v1/data/symbols`
- **Gap**: Trading Desktop widgets (OTC, Venues, Prices) use legacy client that expects endpoints not implemented

### Work Required
1. **Frontend-only fixes (immediate)**: Update Trading Desktop widgets to use spine client + graceful degradation
2. **Backend additions (optional)**: Add symbol detail endpoint for OTC historical data
3. **Feature gating**: Show "not available in Basic" for price charts and venue scores

---

## 2. Page-by-Page Contract Map

### 2.1 Overview Page (`/dashboard`)

| Data Needed | Source | Endpoint | Status | Tier |
|-------------|--------|----------|--------|------|
| Pipeline count | Backend | `GET /v1/pipelines` | ✅ Works | Basic |
| Available weeks count | Backend | `GET /v1/data/weeks?tier=OTC` | ✅ Works | Basic |
| Latest week date | Backend | `GET /v1/data/weeks?tier=OTC&limit=1` | ✅ Works | Basic |
| Success rate (24h) | Backend | Execution history | ❌ Not in Basic | Intermediate |
| Queue depths | Backend | Queue endpoints | ❌ Not in Basic | Intermediate |

**Current FE Code**: Uses `spineClient.listPipelines()` and `spineClient.queryWeeks()` ✅

**Changes Required**: None - already works correctly.

---

### 2.2 Pipelines Page (`/dashboard/pipelines`)

| Data Needed | Source | Endpoint | Status | Tier |
|-------------|--------|----------|--------|------|
| Pipeline list | Backend | `GET /v1/pipelines` | ✅ Works | Basic |
| Pipeline details | Backend | `GET /v1/pipelines/{name}` | ✅ Works | Basic |
| Run pipeline | Backend | `POST /v1/pipelines/{name}/run` | ✅ Works | Basic |
| Execution history | Backend | Execution endpoints | ❌ Not in Basic | Intermediate |

**Current FE Code**: Uses `spineClient.listPipelines()`, `describePipeline()`, `runPipeline()` ✅

**Changes Required**: None - already works correctly.

---

### 2.3 Data Assets Page (`/dashboard/data-assets`)

| Data Needed | Source | Endpoint | Status | Tier |
|-------------|--------|----------|--------|------|
| Available weeks by tier | Backend | `GET /v1/data/weeks?tier=...` | ✅ Works | Basic |
| Top symbols for week | Backend | `GET /v1/data/symbols?tier=...&week=...` | ✅ Works | Basic |
| Symbol volume breakdown | Backend | Calc endpoint | 📋 Proposed | Basic |
| Data readiness | Backend | Readiness endpoint | 📋 Proposed | Intermediate |
| Anomalies | Backend | Anomalies endpoint | 📋 Proposed | Intermediate |

**Current FE Code**: Uses `spineClient.queryWeeks()` and `spineClient.querySymbols()` ✅

**Changes Required**: None for Basic - already works correctly.

---

### 2.4 Settings Page (`/dashboard/settings`)

| Data Needed | Source | Endpoint | Status | Tier |
|-------------|--------|----------|--------|------|
| Backend version | Backend | `GET /v1/capabilities` | ✅ Works | Basic |
| API base URL | FE Config | Environment variable | ✅ Works | Basic |
| Storage stats | Backend | `GET /v1/ops/storage` | ❌ Not implemented | Basic+ |
| API keys | Backend | Auth endpoints | ❌ Not in Basic | Full |

**Current FE Code**: Hardcoded values, reads env vars ⚠️

**Changes Required**: 
- Fetch version from `/v1/capabilities` 
- Mark API keys as "Not available in Basic tier"

---

### 2.5 Trading Desktop (`/`)

| Data Needed | Source | Endpoint | Status | Tier |
|-------------|--------|----------|--------|------|
| Price candles | Backend | `POST /api/v1/query` (prices) | ❌ Endpoint doesn't exist | External data source |
| OTC weekly history | Backend | `POST /api/v1/query` (otc_transparency) | ❌ Endpoint doesn't exist | Basic (need new endpoint) |
| OTC top volume | Backend | `POST /api/v1/query` (otc_top_volume) | ❌ Endpoint doesn't exist | Basic (need new endpoint) |
| Venue scores | Backend | `POST /api/v1/query` (venues) | ❌ Endpoint doesn't exist | External data source |
| Symbols list | Backend | `POST /api/v1/query` (symbols) | ❌ Endpoint doesn't exist | Basic (can adapt) |

**Current FE Code**: Uses legacy `client.ts` with `api.query()` - BROKEN ❌

**Changes Required**:
1. **Price Chart**: Show "Price data not available in Basic tier" (requires external data source)
2. **Venue Scores**: Show "Venue data not available in Basic tier" (requires external data source)
3. **OTC Volume**: Rewire to use `/v1/data/symbols` for top volume, add new endpoint for symbol history
4. **Watchlist**: Implement using local storage (no backend needed)
5. **Ticker Input**: Works (no backend needed)

---

## 3. Mismatch Inventory

### 3.1 Missing Endpoints

| Endpoint | Frontend Expects | Backend Has | Resolution |
|----------|------------------|-------------|------------|
| `POST /api/v1/query` | Generic query interface | ❌ None | **Remove usage** - use specific endpoints |
| `GET /v1/data/calcs/{name}` | Calc queries | ❌ None | 📋 Proposed for future |
| `GET /v1/data/readiness` | Readiness status | ❌ None | 📋 Proposed for Intermediate |
| `GET /v1/data/anomalies` | Quality issues | ❌ None | 📋 Proposed for Intermediate |
| Symbol history endpoint | OTC widget | ❌ None | **Add new endpoint** |

### 3.2 Wrong Field Names/Types

| Location | Frontend Expects | Backend Returns | Resolution |
|----------|------------------|-----------------|------------|
| OTC data | `week_start_date` | N/A | Map from `week_ending` |
| OTC data | `shares` | `volume` | Frontend adapter |
| OTC data | `pct_change_wow` | N/A | Compute client-side or add to endpoint |
| OTC data | `volume_rank` | N/A | Compute client-side or add to endpoint |

### 3.3 Wrong Query Semantics

| Issue | Description | Resolution |
|-------|-------------|------------|
| POST vs GET | Legacy client uses POST for queries | Use GET endpoints |
| Dataset parameter | Legacy uses `dataset: 'otc_transparency'` | Use specific endpoint |

### 3.4 API Key Assumptions

- Settings page shows API key management UI
- Basic tier has no authentication
- **Resolution**: Disable API key UI in Basic tier

### 3.5 Dead UI (Cannot Work in Basic)

| Component | Why | Resolution |
|-----------|-----|------------|
| Price Chart | No price data source | Show "Not available in Basic tier" message |
| Venue Scores | No venue data source | Show "Not available in Basic tier" message |
| API Keys section | No auth in Basic | Hide or show "Requires Full tier" |
| Execution History | No history in Basic | Feature gate already in place ✅ |
| Queue Management | No queues in Basic | Feature gate already in place ✅ |

---

## 4. Resolution Decisions

### 4.1 Frontend Adapter Fixes (Preferred)

| Issue | Fix | Rationale |
|-------|-----|-----------|
| Legacy client usage | Update widgets to use `spineClient` | Clean separation, typed API |
| OTC field mapping | Add adapter in `spineClient` | Keep backend clean |
| Missing price data | Show graceful empty state | No backend work for Basic |
| Missing venue data | Show graceful empty state | No backend work for Basic |

### 4.2 Backend Compatibility Endpoints (If Needed)

None required for Basic tier MVP.

### 4.3 Backend New Endpoints (Required for Basic UX)

| Endpoint | Purpose | Implementation |
|----------|---------|----------------|
| `GET /v1/data/symbols/{symbol}` | Symbol OTC history | Query normalized table, return time series |

---

## 5. Implementation Plan

### Phase 1: Immediate (Basic Tier Working)

#### 5.1 Frontend Changes

1. **Update OTCVolume widget**
   - Replace `useOTCData` with `spineClient.querySymbols()` for top volume
   - Show simplified view (no WoW changes, no historical chart)
   - Add "Symbol history coming soon" message

2. **Update VenueScores widget**
   - Add capability check: if Basic tier, show unavailable message
   - Keep widget structure for future tiers

3. **Update PriceChart widget**
   - Add capability check: if Basic tier, show unavailable message
   - Keep widget structure for Alpha Vantage integration (Phase 2)

4. **Update SettingsPage**
   - Fetch version from capabilities endpoint
   - Disable API keys section in Basic tier
   - Show tier info

#### 5.2 Backend Changes (Optional but Recommended)

1. **Add symbol detail endpoint**
   ```
   GET /v1/data/symbols/{symbol}/history?tier=...&weeks=12
   ```
   Returns weekly OTC data for a specific symbol.

### Phase 2: Alpha Vantage Integration

1. Create `market_data.prices` domain
2. Implement Alpha Vantage source adapter
3. Add price endpoints:
   - `GET /v1/data/prices/{symbol}?days=30`
   - `GET /v1/data/prices/{symbol}/latest`
4. Update PriceChart widget to use new endpoints

### Phase 3: Intermediate Tier

1. Add execution history endpoints
2. Add readiness endpoint
3. Add anomalies endpoint
4. Add scheduling endpoints
5. Update dashboard to use full features

---

## 6. API Contract Summary

### Existing Endpoints (Working)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/v1/capabilities` | Feature discovery |
| GET | `/v1/pipelines` | List pipelines |
| GET | `/v1/pipelines/{name}` | Pipeline details |
| POST | `/v1/pipelines/{name}/run` | Execute pipeline |
| GET | `/v1/data/weeks?tier=...` | List available weeks |
| GET | `/v1/data/symbols?tier=...&week=...&top=...` | Top symbols |

### Proposed Endpoints (Phase 1)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/data/symbols/{symbol}/history?tier=...&weeks=12` | Symbol OTC history |

### Proposed Endpoints (Phase 2+)

| Method | Endpoint | Description | Tier |
|--------|----------|-------------|------|
| GET | `/v1/data/prices/{symbol}` | Price history | Basic+ |
| GET | `/v1/data/calcs` | List calculations | Intermediate |
| GET | `/v1/data/calcs/{name}` | Query calc | Intermediate |
| GET | `/v1/data/readiness` | Data readiness | Intermediate |
| GET | `/v1/data/anomalies` | Quality issues | Intermediate |

---

## 7. How to Demo

### Prerequisites

1. Start backend and frontend (Docker):
   ```powershell
   # From c:\projects\spine-core\market-spine-basic
   docker compose up -d
   ```
   - API: http://localhost:8100
   - Frontend: http://localhost:3100

2. Run a pipeline to ingest data:
   ```powershell
   # Ingest Tier 1 data
   Invoke-RestMethod -Method POST "http://localhost:8100/v1/pipelines/finra.otc_transparency.ingest_week/run" `
     -ContentType "application/json" `
     -Body '{"params": {"week_ending": "2025-12-22", "tier": "NMS_TIER_1", "file": "data/finra/finra_otc_weekly_tier1_20251222.csv"}}'
   
   # Ingest OTC data
   Invoke-RestMethod -Method POST "http://localhost:8100/v1/pipelines/finra.otc_transparency.ingest_week/run" `
     -ContentType "application/json" `
     -Body '{"params": {"week_ending": "2025-12-22", "tier": "OTC", "file": "data/finra/finra_otc_weekly_otc_20251222.csv"}}'
   ```

3. Open frontend: http://localhost:3100

### Demo Walkthrough

1. **Dashboard Overview** (`/dashboard`):
   - Shows pipeline count, data weeks, tier capabilities
   - Connection status indicator (green = connected)
   - Tier displayed as "basic"

2. **Pipelines Page** (`/dashboard/pipelines`):
   - List all available pipelines
   - Click "Run" to execute with parameters
   - Check execution status

3. **Data Assets** (`/dashboard/data-assets`):
   - Select tier tab (NMS Tier 1, Tier 2, OTC)
   - Click a week to see top symbols
   - Symbols table with volume and rank

4. **Trading Desktop** (`/`):
   - **OTC Volume widget**: Shows top symbols from ingested data
     - Click a symbol to see details
     - Shows "Historical data requires Intermediate tier" note
   - **Price Chart**: Shows "Not available in Basic tier" placeholder
   - **Venue Scores**: Shows "Not available in Basic tier" placeholder
   - **Watchlist**: Functional (local storage)
   - **Ticker Input**: Functional

5. **Settings Page** (`/dashboard/settings`):
   - API Version shows backend version from capabilities
   - Tier shows "basic"
   - Connection status indicator
   - API Keys section shows "Requires Advanced tier"

### Testing the Integration

#### Quick Health Check
```powershell
# Test API is up
Invoke-RestMethod http://localhost:8100/health

# Test capabilities
Invoke-RestMethod http://localhost:8100/v1/capabilities

# Test pipelines
Invoke-RestMethod http://localhost:8100/v1/pipelines

# Test data - list weeks
Invoke-RestMethod "http://localhost:8100/v1/data/weeks?tier=OTC"

# Test data - list symbols
Invoke-RestMethod "http://localhost:8100/v1/data/symbols?tier=OTC&week=2025-12-22&top=10"
```

#### Frontend Testing
1. Open DevTools Network tab
2. Navigate through pages
3. Verify requests go to correct endpoints
4. Check for 4xx/5xx errors in console

---

## 8. Technical Notes

### Frontend Architecture

```
trading-desktop/src/
├── api/
│   ├── client.ts         # LEGACY - DO NOT USE
│   ├── hooks.ts          # LEGACY - DO NOT USE
│   ├── spineClient.ts    # ✅ Primary client
│   ├── spineTypes.ts     # ✅ Type definitions
│   └── spineContext.tsx  # ✅ React context
├── dashboard/pages/      # Dashboard pages (use spineClient) ✅
├── widgets/              # Trading widgets (UPDATED) ✅
│   ├── OTCVolume/        # Now uses spineClient
│   ├── PriceChart/       # Shows tier unavailable message
│   └── VenueScores/      # Shows tier unavailable message
└── TradingDesktop.tsx    # Main trading view
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `VITE_API_URL` | Legacy API base URL | `` |
| `VITE_MARKET_SPINE_URL` | Spine API base URL | `` |

Both should point to the same backend (e.g., `http://localhost:8100`).

---

## 9. Acceptance Criteria

### Phase 1 Completed ✅

- [x] Overview page loads without errors
- [x] Pipelines page shows list and allows execution
- [x] Data Assets shows weeks and symbols for all tiers
- [x] Trading Desktop shows graceful "unavailable" states for price/venue widgets
- [x] OTC Volume widget shows top symbols from ingested data
- [x] Settings page shows backend version, tier, and connection status
- [x] No console errors when database is empty
- [x] Empty state messages guide user to run pipeline
- [x] API Keys section disabled in Basic tier

### Files Modified

| File | Change |
|------|--------|
| `trading-desktop/src/api/spineTypes.ts` | Added `OTCWeeklyData`, `FeatureUnavailable`, `DataResult` types |
| `trading-desktop/src/api/spineClient.ts` | Added `getTopOTCSymbols()`, `getSymbolOTCData()` methods |
| `trading-desktop/src/widgets/OTCVolume/OTCVolume.tsx` | Rewired to use spineClient, added tier messaging |
| `trading-desktop/src/widgets/VenueScores/VenueScores.tsx` | Added tier check, shows Advanced tier message |
| `trading-desktop/src/widgets/PriceChart/PriceChart.tsx` | Added tier check, shows Intermediate tier message |
| `trading-desktop/src/dashboard/pages/SettingsPage.tsx` | Shows API version, tier, connection status; disables API keys |

### Phase 1.5 Completed (2026-01-05)

| File | Change |
|------|--------|
| `market-spine-basic/src/market_spine/api/routes/v1/pipelines.py` | Added `GET /v1/data/symbols/{symbol}/history` |
| `market-spine-basic/src/market_spine/api/routes/v1/ops.py` | Added `GET /v1/ops/storage`, `GET /v1/ops/captures` |
| `trading-desktop/src/api/spineTypes.ts` | Added `SymbolWeekData`, `QuerySymbolHistoryResponse`, `StorageStatsResponse`, `CaptureInfo`, `CapturesListResponse` |
| `trading-desktop/src/api/spineClient.ts` | Added `getSymbolHistory()`, `getStorageStats()`, `listCaptures()` |
| `trading-desktop/src/components/ErrorBoundary.tsx` | Created ErrorBoundary, WidgetErrorBoundary |
| `trading-desktop/src/components/Skeleton.tsx` | Created loading skeleton components |
| `trading-desktop/src/components/EmptyState.tsx` | Created NoDataEmptyState, ConnectionErrorEmptyState |
| `trading-desktop/src/dashboard/pages/OverviewPage.tsx` | Added Database Size stat card |
| `trading-desktop/src/dashboard/pages/SettingsPage.tsx` | Added Storage Statistics, Data Captures sections |
| `trading-desktop/src/dashboard/pages/DataAssetsPage.tsx` | Added symbol history panel with URL filter support |
| `trading-desktop/src/widgets/OTCVolume/OTCVolume.tsx` | Added View History button linking to Data Assets |
| `docs/api/02-basic-api-surface.md` | Updated to v1.1 with new endpoints |

### Next Steps (Phase 2)

- [x] Add symbol history endpoint to backend ✅ *2026-01-04*
- [x] Add OTC historical chart to OTC widget ✅ *2026-01-05* (links to Data Assets)
- [ ] Integrate Alpha Vantage for price data (Intermediate tier)
- [ ] Add execution history (Intermediate tier)
