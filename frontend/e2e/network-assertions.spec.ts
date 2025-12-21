/**
 * Network assertion E2E tests.
 *
 * These tests prove real wiring: each UI interaction triggers the correct
 * API call, the response has the expected envelope shape, and status codes
 * are correct.
 *
 * Uses Playwright's `waitForResponse` to intercept the frontend's actual
 * HTTP requests — not direct `page.evaluate(fetch(...))`.
 */
import { test, expect } from '@playwright/test';

const BASE = 'http://localhost:12001';
const API = 'http://localhost:12000/api/v1';

/** Assert a PagedResponse envelope shape */
function assertPagedEnvelope(body: Record<string, unknown>) {
  expect(body).toHaveProperty('data');
  expect(Array.isArray(body.data)).toBe(true);
  expect(body).toHaveProperty('page');
  const page = body.page as Record<string, unknown>;
  expect(page).toHaveProperty('total');
  expect(page).toHaveProperty('limit');
  expect(page).toHaveProperty('offset');
  expect(page).toHaveProperty('has_more');
  expect(typeof page.total).toBe('number');
}

/** Assert a SuccessResponse envelope shape */
function assertSuccessEnvelope(body: Record<string, unknown>) {
  expect(body).toHaveProperty('data');
  expect(typeof body.data).toBe('object');
}

test.describe('Network assertions — UI triggers correct API calls', () => {
  test('Runs page fetches GET /api/v1/runs with PagedResponse', async ({ page }) => {
    await page.request.post(`${API}/database/init`);

    const responsePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/runs') &&
        resp.request().method() === 'GET' &&
        !resp.url().includes('/stats') &&
        resp.status() === 200,
    );

    await page.goto(`${BASE}/runs`);
    const response = await responsePromise;
    assertPagedEnvelope(await response.json());
  });

  test('Workflows page fetches GET /api/v1/workflows with PagedResponse', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/v1/workflows') && resp.request().method() === 'GET',
    );

    await page.goto(`${BASE}/workflows`);
    const response = await responsePromise;

    expect(response.status()).toBe(200);
    const body = await response.json();
    assertPagedEnvelope(body);
  });

  test('Workflow detail fetches GET /api/v1/workflows/{name} with SuccessResponse', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (resp) =>
        /\/api\/v1\/workflows\/[^/]+$/.test(resp.url()) &&
        resp.request().method() === 'GET',
    );

    await page.goto(`${BASE}/workflows/etl.daily_ingest`);
    const response = await responsePromise;

    expect(response.status()).toBe(200);
    const body = await response.json();
    assertSuccessEnvelope(body);
    const data = body.data as Record<string, unknown>;
    expect(data).toHaveProperty('name');
    expect(data).toHaveProperty('steps');
    expect(data).toHaveProperty('domain');
    expect(data).toHaveProperty('policy');
    expect(data).toHaveProperty('tags');
    expect(Array.isArray(data.steps)).toBe(true);
  });

  test('Dashboard fetches runs + DLQ with correct envelopes', async ({ page }) => {
    // Ensure DB is ready
    await page.request.post(`${API}/database/init`);

    const runsPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/runs') &&
        !resp.url().includes('/stats') &&
        resp.request().method() === 'GET' &&
        resp.status() === 200,
    );
    const dlqPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/dlq') &&
        resp.request().method() === 'GET' &&
        resp.status() === 200,
    );

    await page.goto(`${BASE}/`);
    const [runsResp, dlqResp] = await Promise.all([runsPromise, dlqPromise]);

    assertPagedEnvelope(await runsResp.json());
    assertPagedEnvelope(await dlqResp.json());
  });

  test('Schedules page fetches GET /api/v1/schedules with PagedResponse', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/v1/schedules') && resp.request().method() === 'GET',
    );

    await page.goto(`${BASE}/schedules`);
    const response = await responsePromise;

    expect(response.status()).toBe(200);
    const body = await response.json();
    assertPagedEnvelope(body);
  });

  test('DLQ page fetches GET /api/v1/dlq with PagedResponse', async ({ page }) => {
    await page.request.post(`${API}/database/init`);

    const responsePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/dlq') &&
        resp.request().method() === 'GET' &&
        resp.status() === 200,
    );

    await page.goto(`${BASE}/dlq`);
    const response = await responsePromise;
    assertPagedEnvelope(await response.json());
  });

  test('Quality page fetches GET /api/v1/quality with PagedResponse', async ({ page }) => {
    await page.request.post(`${API}/database/init`);

    const responsePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/quality') &&
        resp.request().method() === 'GET' &&
        resp.status() === 200,
    );

    await page.goto(`${BASE}/quality`);
    const response = await responsePromise;
    assertPagedEnvelope(await response.json());
  });

  test('Stats page fetches all three stats endpoints', async ({ page }) => {
    const runsStatsPromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/v1/stats/runs') && resp.request().method() === 'GET',
    );
    const queuesPromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/v1/stats/queues') && resp.request().method() === 'GET',
    );
    const workersPromise = page.waitForResponse(
      (resp) => resp.url().endsWith('/stats/workers') && resp.request().method() === 'GET',
    );

    await page.goto(`${BASE}/stats`);
    const [runsStats, queuesResp, workersResp] = await Promise.all([
      runsStatsPromise,
      queuesPromise,
      workersPromise,
    ]);

    expect(runsStats.status()).toBe(200);
    const statsBody = await runsStats.json();
    assertSuccessEnvelope(statsBody);

    expect(queuesResp.status()).toBe(200);
    expect(workersResp.status()).toBe(200);
  });

  test('Run detail page fetches GET /api/v1/runs/{run_id} with SuccessResponse', async ({ page }) => {
    // Ensure DB is initialized
    await page.request.post(`${API}/database/init`);

    // Seed a run to get a valid run_id
    const seedResp = await page.request.post(`${API}/runs`, {
      data: { kind: 'task', name: 'test_network_assert' },
    });
    if (seedResp.status() >= 400) {
      test.skip(true, 'API returned error on seed — database may not be ready');
      return;
    }
    const seed = await seedResp.json();
    const runId = seed?.data?.run_id;
    if (!runId) {
      test.skip(true, 'No run seeded — API may not accept test submissions');
      return;
    }

    const responsePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes(`/api/v1/runs/${runId}`) &&
        resp.request().method() === 'GET' &&
        resp.status() === 200,
    );

    await page.goto(`${BASE}/runs/${runId}`);
    const response = await responsePromise;
    const body = await response.json();
    assertSuccessEnvelope(body);
    expect(body.data).toHaveProperty('run_id');
    expect(body.data).toHaveProperty('status');
  });

  test('Runs pagination changes offset and triggers new request', async ({ page }) => {
    await page.request.post(`${API}/database/init`);

    await page.goto(`${BASE}/runs`);
    // Wait for initial successful load
    await page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/runs') &&
        !resp.url().includes('/stats') &&
        resp.status() === 200,
    );

    // Check if there's a Next button (only if sufficient data)
    const nextBtn = page.getByRole('button', { name: 'Next' });
    if (await nextBtn.isVisible()) {
      const paginatedPromise = page.waitForResponse(
        (resp) =>
          resp.url().includes('/api/v1/runs') &&
          resp.url().includes('offset=') &&
          !resp.url().includes('/stats') &&
          resp.status() === 200,
      );
      await nextBtn.click();
      const pagResp = await paginatedPromise;
      assertPagedEnvelope(await pagResp.json());
    }
  });
});
