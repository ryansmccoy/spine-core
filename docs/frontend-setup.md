# Frontend Setup Guide

This guide explains how to configure the Trading Desktop frontend to connect to Market Spine backends.

## Overview

The Trading Desktop is designed to work with multiple Market Spine backend tiers:

| Backend | Profile | Features |
|---------|---------|----------|
| **Basic** | `basic` | Pipelines, weeks/symbols queries |
| **Intermediate** | `intermediate` | + Scheduler, calc queries |
| **Advanced** | `advanced` | + Anomaly detection, readiness scoring, multi-version |

The frontend automatically detects available features via the `/v1/capabilities` endpoint and shows/hides UI elements accordingly.

## Quick Start

### 1. Copy Environment File

```bash
cp .env.local.example .env.local
```

### 2. Configure Backend URL

Edit `.env.local`:

```env
# Point to your Market Spine backend
VITE_MARKET_SPINE_BASE_URL=http://localhost:8000

# Optional: Override profile detection
# VITE_MARKET_SPINE_PROFILE=basic
```

### 3. Start Development Server

```bash
npm install
npm run dev
```

The frontend will start at `http://localhost:5173` with automatic proxy to the backend.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_MARKET_SPINE_BASE_URL` | Yes | `http://localhost:8000` | Backend API base URL |
| `VITE_MARKET_SPINE_PROFILE` | No | (auto-detect) | Force a specific profile: `basic`, `intermediate`, `advanced` |

## Backend Profiles

### Basic Backend

The Basic backend provides core pipeline and query functionality:

**Available Features:**
- ✅ Health check
- ✅ Capabilities endpoint
- ✅ List/describe/run pipelines
- ✅ Query weeks by tier
- ✅ Query symbols by tier and week

**Unavailable Features (hidden in UI):**
- ❌ Scheduler / job management
- ❌ Calculation queries
- ❌ Anomaly detection
- ❌ Readiness scoring
- ❌ Multi-version support

### Intermediate Backend

Adds scheduling and calculation features:

**Additional Features:**
- ✅ Scheduler with job queue
- ✅ Calculation query endpoints
- ✅ Basic anomaly flagging

### Advanced Backend

Full-featured backend with all capabilities:

**Additional Features:**
- ✅ Advanced anomaly detection
- ✅ Readiness scoring
- ✅ Multi-version data access
- ✅ Real-time updates

## Development Configuration

### Vite Proxy

The `vite.config.ts` includes a proxy configuration to avoid CORS issues during development:

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, ''),
    },
  },
}
```

This means you can set `VITE_MARKET_SPINE_BASE_URL=/api` to use the proxy.

### Mock Mode

For UI development without a running backend, the frontend includes graceful degradation:

1. If backend is unreachable, the connection banner shows "Disconnected"
2. Feature-gated components hide unavailable features
3. Error states are displayed gracefully

## Troubleshooting

### CORS Errors

**Symptom:** Browser console shows `Access-Control-Allow-Origin` errors.

**Solutions:**

1. **Use the Vite proxy** (recommended for development):
   ```env
   VITE_MARKET_SPINE_BASE_URL=/api
   ```

2. **Enable CORS on backend** (if you control the backend):
   The Basic backend includes CORS middleware by default.

3. **Check backend is running:**
   ```bash
   curl http://localhost:8000/health
   ```

### "Disconnected" Banner

**Symptom:** Frontend shows "Disconnected from Market Spine" banner.

**Checks:**

1. Is the backend running?
   ```bash
   curl http://localhost:8000/health
   ```

2. Is the URL correct in `.env.local`?

3. Check browser console for network errors.

4. If using Docker, ensure ports are exposed correctly.

### Missing Features

**Symptom:** Some UI elements are hidden or show "Upgrade to X tier" messages.

**Explanation:** The frontend uses capability detection. Features are hidden when the backend's `/v1/capabilities` response indicates they're unavailable.

**Verify capabilities:**
```bash
curl http://localhost:8000/v1/capabilities
```

Expected response for Basic:
```json
{
  "profile": "basic",
  "version": "1.0.0",
  "features": {
    "pipelines": true,
    "query_weeks": true,
    "query_symbols": true,
    "query_calcs": false,
    "scheduler": false,
    "anomaly_detection": false,
    "readiness_scoring": false,
    "multi_version": false
  }
}
```

### TypeScript Errors

**Symptom:** Build fails with type errors.

**Solution:**
```bash
# Check types
npx tsc --noEmit

# If errors persist, regenerate node_modules
rm -rf node_modules
npm install
```

## API Client Architecture

The frontend uses a layered API client architecture:

```
┌─────────────────────────────────────────┐
│           React Components              │
│    (pages, widgets, dashboards)         │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│          SpineContext (React)           │
│  - Connection state                     │
│  - Capabilities caching                 │
│  - Feature gating (FeatureGate)         │
│  - useSpine() hook                      │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│          SpineClient (TypeScript)       │
│  - Typed API methods                    │
│  - Error normalization                  │
│  - Request tracing (x-request-id)       │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│           fetch() / HTTP                │
└─────────────────────────────────────────┘
```

### Using the API

**In React components:**

```tsx
import { useSpine, FeatureGate } from '../api';

function MyComponent() {
  const { client, hasFeature, isConnected } = useSpine();

  // Check feature availability
  if (!hasFeature('query_calcs')) {
    return <div>Calculation queries not available</div>;
  }

  // Use client methods
  const handleQuery = async () => {
    const result = await client.queryWeeks('otc');
    console.log(result);
  };

  return <button onClick={handleQuery}>Query</button>;
}

// Or use FeatureGate for declarative gating
function MyPage() {
  return (
    <FeatureGate 
      feature="scheduler" 
      fallback={<UpgradePrompt tier="intermediate" />}
    >
      <SchedulerDashboard />
    </FeatureGate>
  );
}
```

## Running Tests

```bash
# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Run specific test file
npm test -- src/api/__tests__/spineClient.test.ts
```

## Production Build

```bash
# Build for production
npm run build

# Preview production build
npm run preview
```

For production deployment, set environment variables appropriately:

```env
VITE_MARKET_SPINE_BASE_URL=https://api.yourcompany.com
```
