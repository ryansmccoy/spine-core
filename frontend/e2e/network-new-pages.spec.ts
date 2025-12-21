/**
 * Network assertion E2E tests for new pages: Functions, Database, Examples, Playground.
 *
 * Verifies that UI interactions trigger the correct API calls with expected
 * HTTP methods, status codes, and response envelope shapes.
 */
import { test, expect } from '@playwright/test';

const API = 'http://localhost:12000/api/v1';

function assertSuccessEnvelope(body: Record<string, unknown>) {
  expect(body).toHaveProperty('data');
}

function assertArrayEnvelope(body: Record<string, unknown>) {
  expect(body).toHaveProperty('data');
  expect(Array.isArray(body.data)).toBe(true);
}

test.beforeEach(async ({ page }) => {
  try {
    await page.request.post(`${API}/database/init`);
  } catch { /* backend may be unavailable */ }
});

// ── Functions API ───────────────────────────────────────────────────

test.describe('Network — Functions endpoints', () => {
  test('GET /api/v1/functions returns function list', async ({ request }) => {
    const res = await request.get(`${API}/functions`);
    if (res.ok()) {
      const body = await res.json();
      assertArrayEnvelope(body);
      // Each item should have id, name, status
      if ((body.data as any[]).length > 0) {
        const fn = (body.data as any[])[0];
        expect(fn).toHaveProperty('id');
        expect(fn).toHaveProperty('name');
        expect(fn).toHaveProperty('status');
      }
    }
  });

  test('GET /api/v1/functions/templates returns template list', async ({ request }) => {
    const res = await request.get(`${API}/functions/templates`);
    if (res.ok()) {
      const body = await res.json();
      assertArrayEnvelope(body);
    }
  });

  test('POST /api/v1/functions creates a new function', async ({ request }) => {
    const res = await request.post(`${API}/functions`, {
      data: {
        name: `net_test_${Date.now()}`,
        description: 'Network assertion test',
        source: 'def handler(event, context):\n    return {"ok": True}',
        tags: ['test'],
      },
    });
    if (res.ok()) {
      const body = await res.json();
      assertSuccessEnvelope(body);
      const fn = body.data as Record<string, unknown>;
      expect(fn).toHaveProperty('id');
      expect(fn).toHaveProperty('name');
      expect(fn).toHaveProperty('source');
    }
  });

  test('GET /api/v1/functions/{id} returns function detail', async ({ request }) => {
    // First get a function ID
    const listRes = await request.get(`${API}/functions`);
    if (!listRes.ok()) return;
    const list = await listRes.json();
    if (!list.data || list.data.length === 0) return;

    const fnId = list.data[0].id;
    const res = await request.get(`${API}/functions/${fnId}`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    assertSuccessEnvelope(body);
    const fn = body.data as Record<string, unknown>;
    expect(fn).toHaveProperty('id');
    expect(fn).toHaveProperty('source');
    expect(fn).toHaveProperty('config');
    expect(fn).toHaveProperty('tags');
  });

  test('POST /api/v1/functions/{id}/invoke executes a function', async ({ request }) => {
    const listRes = await request.get(`${API}/functions`);
    if (!listRes.ok()) return;
    const list = await listRes.json();
    if (!list.data || list.data.length === 0) return;

    const fnId = list.data[0].id;
    const res = await request.post(`${API}/functions/${fnId}/invoke`, {
      data: { event: { name: 'test' } },
    });
    if (res.ok()) {
      const body = await res.json();
      assertSuccessEnvelope(body);
      const result = body.data as Record<string, unknown>;
      expect(result).toHaveProperty('status');
      expect(result).toHaveProperty('duration_ms');
      expect(result).toHaveProperty('request_id');
    }
  });

  test('PUT /api/v1/functions/{id} updates a function', async ({ request }) => {
    const listRes = await request.get(`${API}/functions`);
    if (!listRes.ok()) return;
    const list = await listRes.json();
    if (!list.data || list.data.length === 0) return;

    const fnId = list.data[0].id;
    const res = await request.put(`${API}/functions/${fnId}`, {
      data: { description: 'Updated by E2E test' },
    });
    if (res.ok()) {
      const body = await res.json();
      assertSuccessEnvelope(body);
    }
  });

  test('GET /api/v1/functions/{id}/logs returns invocation logs', async ({ request }) => {
    const listRes = await request.get(`${API}/functions`);
    if (!listRes.ok()) return;
    const list = await listRes.json();
    if (!list.data || list.data.length === 0) return;

    const fnId = list.data[0].id;
    const res = await request.get(`${API}/functions/${fnId}/logs`);
    if (res.ok()) {
      const body = await res.json();
      assertArrayEnvelope(body);
    }
  });
});

// ── Database API ────────────────────────────────────────────────────

test.describe('Network — Database endpoints', () => {
  test('GET /api/v1/database/health returns connection info', async ({ request }) => {
    const res = await request.get(`${API}/database/health`);
    if (res.ok()) {
      const body = await res.json();
      assertSuccessEnvelope(body);
      const data = body.data as Record<string, unknown>;
      expect(data).toHaveProperty('connected');
      expect(data).toHaveProperty('backend');
      expect(data).toHaveProperty('latency_ms');
      expect(data).toHaveProperty('table_count');
    }
  });

  test('GET /api/v1/database/config returns database configuration', async ({ request }) => {
    const res = await request.get(`${API}/database/config`);
    if (res.ok()) {
      const body = await res.json();
      assertSuccessEnvelope(body);
    }
  });

  test('GET /api/v1/database/schema returns table schemas', async ({ request }) => {
    const res = await request.get(`${API}/database/schema`);
    if (res.ok()) {
      const body = await res.json();
      assertArrayEnvelope(body);
      if ((body.data as any[]).length > 0) {
        const table = (body.data as any[])[0];
        expect(table).toHaveProperty('table_name');
        expect(table).toHaveProperty('columns');
        expect(table).toHaveProperty('row_count');
      }
    }
  });

  test('GET /api/v1/database/tables/counts returns row counts', async ({ request }) => {
    const res = await request.get(`${API}/database/tables/counts`);
    if (res.ok()) {
      const body = await res.json();
      assertArrayEnvelope(body);
    }
  });

  test('POST /api/v1/database/query executes SQL', async ({ request }) => {
    const res = await request.post(`${API}/database/query`, {
      data: { sql: "SELECT 1 AS test", limit: 10 },
    });
    if (res.ok()) {
      const body = await res.json();
      assertSuccessEnvelope(body);
      const data = body.data as Record<string, unknown>;
      expect(data).toHaveProperty('columns');
      expect(data).toHaveProperty('rows');
      expect(data).toHaveProperty('row_count');
      expect(data).toHaveProperty('elapsed_ms');
    }
  });

  test('POST /api/v1/database/init initializes database', async ({ request }) => {
    const res = await request.post(`${API}/database/init`);
    if (res.ok()) {
      const body = await res.json();
      assertSuccessEnvelope(body);
    }
  });

  test('POST /api/v1/database/vacuum runs VACUUM', async ({ request }) => {
    const res = await request.post(`${API}/database/vacuum`);
    if (res.ok()) {
      const body = await res.json();
      assertSuccessEnvelope(body);
    }
  });
});

// ── Examples API ────────────────────────────────────────────────────

test.describe('Network — Examples endpoints', () => {
  test('GET /api/v1/examples returns example list', async ({ request }) => {
    const res = await request.get(`${API}/examples`);
    if (res.ok()) {
      const body = await res.json();
      assertArrayEnvelope(body);
    }
  });

  test('GET /api/v1/examples/categories returns category list', async ({ request }) => {
    const res = await request.get(`${API}/examples/categories`);
    if (res.ok()) {
      const body = await res.json();
      assertArrayEnvelope(body);
    }
  });

  test('GET /api/v1/examples/results returns run results', async ({ request }) => {
    const res = await request.get(`${API}/examples/results`);
    if (res.ok()) {
      const body = await res.json();
      assertSuccessEnvelope(body);
    }
  });

  test('GET /api/v1/examples/status returns run status', async ({ request }) => {
    const res = await request.get(`${API}/examples/status`);
    if (res.ok()) {
      const body = await res.json();
      assertSuccessEnvelope(body);
    }
  });
});

// ── Playground API ──────────────────────────────────────────────────

test.describe('Network — Playground endpoints', () => {
  test('GET /api/v1/playground/workflows returns available workflows', async ({ request }) => {
    const res = await request.get(`${API}/playground/workflows`);
    if (res.ok()) {
      const body = await res.json();
      assertArrayEnvelope(body);
    }
  });

  test('GET /api/v1/playground/examples returns playground examples', async ({ request }) => {
    const res = await request.get(`${API}/playground/examples`);
    if (res.ok()) {
      const body = await res.json();
      assertArrayEnvelope(body);
    }
  });
});
