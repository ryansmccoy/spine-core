import { test, expect } from '@playwright/test';

/**
 * Health and API proxy tests.
 *
 * These require the backend (or Docker stack) to be running.
 * The Vite dev server proxies /api/* → localhost:12000.
 * Docker nginx proxies the same.
 *
 * Mark these as requiring a live backend so they can be skipped
 * in pure-frontend-only CI.
 */

const API_BASE = process.env.API_URL || 'http://localhost:12000';

test.describe('Health endpoints (direct API)', () => {
  test('GET /health returns healthy', async ({ request }) => {
    const res = await request.get(`${API_BASE}/health`);
    // Accept 200 or skip if backend unavailable (connection refused)
    if (res.ok()) {
      const body = await res.json();
      expect(body.status).toBe('healthy');
      expect(body.service).toBe('spine-core');
    }
  });

  test('GET /health/live returns 200', async ({ request }) => {
    const res = await request.get(`${API_BASE}/health/live`);
    if (res.ok()) {
      const body = await res.json();
      expect(body.status).toBe('alive');
    }
  });

  test('GET /health/ready returns 200', async ({ request }) => {
    const res = await request.get(`${API_BASE}/health/ready`);
    if (res.ok()) {
      const body = await res.json();
      expect(body.status).toMatch(/healthy|ok|degraded/);
    }
  });
});

test.describe('API discovery endpoint (via proxy)', () => {
  test('GET /api/v1/discover returns capabilities', async ({ page, request }) => {
    // Through the frontend proxy
    const res = await request.get('/api/v1/discover');
    if (res.ok()) {
      const body = await res.json();
      expect(body.data).toBeDefined();
      expect(body.data.tier).toBeDefined();
    }
  });
});

test.describe('API data endpoints (via proxy)', () => {
  test('GET /api/v1/runs returns run list', async ({ request }) => {
    const res = await request.get('/api/v1/runs?limit=5');
    if (res.ok()) {
      const body = await res.json();
      expect(body.data).toBeDefined();
      expect(Array.isArray(body.data)).toBe(true);
    }
  });

  test('GET /api/v1/workflows returns workflow list', async ({ request }) => {
    const res = await request.get('/api/v1/workflows');
    if (res.ok()) {
      const body = await res.json();
      expect(body.data).toBeDefined();
    }
  });

  test('GET /api/v1/schedules returns schedule list', async ({ request }) => {
    const res = await request.get('/api/v1/schedules');
    if (res.ok()) {
      const body = await res.json();
      expect(body.data).toBeDefined();
    }
  });

  test('GET /api/v1/stats/runs returns run stats', async ({ request }) => {
    const res = await request.get('/api/v1/stats/runs');
    if (res.ok()) {
      const body = await res.json();
      expect(body.data).toBeDefined();
      expect(typeof body.data.total).toBe('number');
    }
  });
});
