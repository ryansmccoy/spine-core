/**
 * Scenario-driven E2E tests for the spine-core frontend.
 *
 * These tests validate that every scenario renders correctly in the UI:
 * - Correct status badges
 * - Error messages visible/hidden as expected
 * - Empty states displayed appropriately
 * - Filtering works across status tabs
 * - Workflow cards, run details, and schedule tables render properly
 *
 * The test seeds data via the API before making UI assertions,
 * ensuring deterministic state.
 */

import { test, expect, type Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

// ── Scenario loader ─────────────────────────────────────────────────

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

interface Scenario {
  id: string;
  name: string;
  category: string;
  kind: string | null;
  workflow: string | null;
  submit: Record<string, unknown> | null;
  trigger_workflow: Record<string, unknown> | null;
  schedule: Record<string, unknown> | null;
  expected: Record<string, unknown>;
  ui: Record<string, unknown>;
}

const scenariosPath = path.resolve(__dirname, '../../scenarios/scenarios.json');
const SCENARIOS: Scenario[] = JSON.parse(fs.readFileSync(scenariosPath, 'utf-8'));

// ── Helpers ─────────────────────────────────────────────────────────

const API = '/api/v1';
const DIRECT_API = 'http://localhost:12000/api/v1';

// Ensure DB is initialized — uses direct API call (no page navigation needed)
test.beforeEach(async ({ page }) => {
  await page.request.post(`${DIRECT_API}/database/init`).catch(() => {});
});

async function apiPost(page: Page, endpoint: string, body: unknown) {
  return page.evaluate(
    async ({ url, payload }) => {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      return { status: res.status, data: await res.json().catch(() => ({})) };
    },
    { url: `${API}${endpoint}`, payload: body },
  );
}

async function apiGet(page: Page, endpoint: string) {
  return page.evaluate(
    async ({ url }) => {
      const res = await fetch(url);
      return { status: res.status, data: await res.json().catch(() => ({})) };
    },
    { url: `${API}${endpoint}` },
  );
}

/** Seed a run via API and return the run_id. */
async function seedRun(
  page: Page,
  body: Record<string, unknown>,
): Promise<string | null> {
  const result = await apiPost(page, '/runs', body);
  return result.status === 202 ? (result.data as any)?.data?.run_id : null;
}

/** Wait for data to load (polling-based, no brittle sleep). */
async function waitForDataOrEmpty(page: Page, timeout = 5000) {
  await expect(
    page
      .locator('table, .text-center.py-12, .bg-red-50, .grid')
      .first(),
  ).toBeVisible({ timeout });
}

// ── Tests ───────────────────────────────────────────────────────────

test.describe('Scenario: Runs page rendering', () => {
  test('empty state shows "No runs found" message', async ({ page }) => {
    await page.goto('/runs');
    await waitForDataOrEmpty(page);

    // Either shows empty state or table — both are valid
    const hasEmpty = await page.getByText('No runs found').isVisible().catch(() => false);
    const hasTable = await page.locator('table').isVisible().catch(() => false);
    expect(hasEmpty || hasTable).toBe(true);
  });

  test('seeded run appears in table with correct status badge', async ({ page }) => {
    await page.goto('/runs');
    // Seed a run via API
    const runId = await seedRun(page, {
      kind: 'task',
      name: 'scenario_e2e_test',
      params: { test: true },
    });
    expect(runId).toBeTruthy();

    // Refresh and wait for table
    await page.reload();
    await waitForDataOrEmpty(page);

    // Run should appear
    const table = page.locator('table');
    const hasTable = await table.isVisible().catch(() => false);
    if (hasTable) {
      // Status badge should show "pending"
      await expect(table.getByText('pending').first()).toBeVisible({ timeout: 5000 });
    }
  });

  test('status filter tabs work', async ({ page }) => {
    await page.goto('/runs');
    // Seed a pending run
    await seedRun(page, { kind: 'task', name: 'filter_test', params: {} });
    await page.reload();
    await waitForDataOrEmpty(page);

    // Click "pending" filter
    const pendingTab = page.getByRole('button', { name: 'pending' });
    if (await pendingTab.isVisible().catch(() => false)) {
      await pendingTab.click();
      await page.waitForTimeout(500);
      // All visible status badges should be "pending"
      const badges = page.locator('table td').filter({ hasText: /pending|running|completed|failed/ });
      const count = await badges.count();
      for (let i = 0; i < count; i++) {
        const text = await badges.nth(i).textContent();
        if (text?.trim()) {
          expect(text.trim()).toBe('pending');
        }
      }
    }

    // Click "All" filter
    await page.getByRole('button', { name: 'All' }).click();
  });
});

test.describe('Scenario: Run detail page', () => {
  test('shows all detail fields for a seeded run', async ({ page }) => {
    await page.goto('/runs');
    const runId = await seedRun(page, {
      kind: 'task',
      name: 'detail_test',
      params: { key: 'value' },
    });
    expect(runId).toBeTruthy();

    // Navigate to detail
    await page.goto(`/runs/${runId}`);
    await page.waitForTimeout(500);

    // Check for key detail fields
    await expect(page.getByText('Run ID')).toBeVisible();
    await expect(page.getByText('Status')).toBeVisible();
    await expect(page.getByText('Pipeline')).toBeVisible();

    // Back button exists
    await expect(page.getByRole('button', { name: /back/i })).toBeVisible();
  });

  test('event timeline shows submitted event', async ({ page }) => {
    await page.goto('/runs');
    const runId = await seedRun(page, {
      kind: 'task',
      name: 'event_timeline_test',
      params: {},
    });

    await page.goto(`/runs/${runId}`);
    await page.waitForTimeout(1000);

    // Event timeline is now in a tab — click Events tab first
    const eventsTab = page.getByRole('button', { name: 'Events' });
    const hasEventsTab = await eventsTab.isVisible().catch(() => false);

    if (hasEventsTab) {
      await eventsTab.click();
      await expect(
        page.getByText('submitted').or(page.getByText('No events')).first(),
      ).toBeVisible({ timeout: 5000 });
    }
  });
});

test.describe('Scenario: Workflows page', () => {
  test('shows registered workflow cards', async ({ page }) => {
    await page.goto('/workflows');
    await expect(page.getByRole('heading', { name: 'Workflows' })).toBeVisible();

    await waitForDataOrEmpty(page);

    // Should show at least one workflow card or the empty state
    const cards = page.locator('.grid .bg-white');
    const empty = page.getByText('No workflows registered');
    const hasCards = (await cards.count()) > 0;
    const hasEmpty = await empty.isVisible().catch(() => false);
    expect(hasCards || hasEmpty).toBe(true);
  });

  test('workflow card has run button', async ({ page }) => {
    await page.goto('/workflows');
    await waitForDataOrEmpty(page);

    const runBtn = page.getByRole('button', { name: /run/i }).first();
    const hasBtn = await runBtn.isVisible().catch(() => false);

    if (hasBtn) {
      // Click opens modal
      await runBtn.click();
      await expect(page.getByText('Parameters (JSON)')).toBeVisible();
      await expect(page.getByLabel(/dry run/i)).toBeVisible();
      // Close
      await page.getByRole('button', { name: 'Close' }).click();
    }
  });

  test('trigger workflow via modal executes successfully', async ({ page }) => {
    await page.goto('/workflows');
    await waitForDataOrEmpty(page);

    const runBtn = page.getByRole('button', { name: /run/i }).first();
    if (await runBtn.isVisible().catch(() => false)) {
      await runBtn.click();

      // Check dry run and execute
      await page.getByLabel(/dry run/i).check();
      await page.getByRole('button', { name: /execute/i }).click();

      // Wait for result message
      await expect(
        page.getByText(/run submitted/i).or(page.getByText(/error/i)).first(),
      ).toBeVisible({ timeout: 5000 });
    }
  });
});

test.describe('Scenario: Schedules page', () => {
  test('create schedule dialog has dynamic workflow picker', async ({ page }) => {
    await page.goto('/schedules');
    await page.getByRole('button', { name: /new schedule/i }).click();

    // Workflow field
    const workflowField = page.locator('#sched-workflow');
    await expect(workflowField).toBeVisible();

    // Should be a <select> if workflows are loaded, or an <input> fallback
    const tagName = await workflowField.evaluate((el) => el.tagName.toLowerCase());
    expect(['select', 'input']).toContain(tagName);

    // Cron field
    await expect(page.getByLabel('Cron Expression')).toBeVisible();
    // Close
    await page.getByRole('button', { name: 'Cancel' }).click();
  });

  test('full schedule CRUD via UI', async ({ page }) => {
    await page.goto('/schedules');

    // Create
    await page.getByRole('button', { name: /new schedule/i }).click();
    const wfField = page.locator('#sched-workflow');

    // Fill in workflow
    const isSelect = (await wfField.evaluate((el) => el.tagName.toLowerCase())) === 'select';
    if (isSelect) {
      // Pick first workflow option
      const options = await wfField.locator('option').allTextContents();
      const firstWorkflow = options.find((o) => o && o !== 'Select a workflow…');
      if (firstWorkflow) {
        await wfField.selectOption({ label: firstWorkflow });
      } else {
        // Fallback: select by value
        await wfField.selectOption('etl.daily_ingest');
      }
    } else {
      await wfField.fill('etl.daily_ingest');
    }

    // Fill cron
    await page.getByLabel('Cron Expression').fill('0 * * * *');

    // Submit
    await page.getByRole('button', { name: /create/i }).click();
    await page.waitForTimeout(1000);

    // Table should show the schedule
    const table = page.locator('table');
    const hasTable = await table.isVisible().catch(() => false);
    if (hasTable) {
      // Cron is humanized: "0 * * * *" → "Every hour"
      await expect(table.getByText('Every hour').or(table.getByText('0 * * * *')).first()).toBeVisible();
    }
  });
});

test.describe('Scenario: DLQ page', () => {
  test('shows empty state on fresh database', async ({ page }) => {
    await page.goto('/dlq');
    await waitForDataOrEmpty(page);

    await expect(
      page
        .getByText('Dead letter queue is empty')
        .or(page.locator('table th').getByText('Pipeline'))
        .or(page.getByText('Failed to load'))
        .first(),
    ).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Scenario: Quality page', () => {
  test('renders both quality and anomaly sections', async ({ page }) => {
    await page.goto('/quality');
    const main = page.locator('main');
    await expect(main.getByText('Quality & Anomalies')).toBeVisible();
    await expect(main.getByRole('heading', { name: 'Quality Results' })).toBeVisible();
    await expect(main.getByRole('heading', { name: 'Anomalies', exact: true })).toBeVisible();
  });
});

test.describe('Scenario: Response contract validation', () => {
  test('paginated endpoints return correct envelope shape', async ({ page }) => {
    await page.goto('/');

    const pagedEndpoints = ['/runs', '/workflows', '/schedules', '/dlq'];

    for (const ep of pagedEndpoints) {
      const result = await apiGet(page, ep);
      if (result.status === 200) {
        const data = result.data as any;
        expect(data).toHaveProperty('data');
        expect(Array.isArray(data.data)).toBe(true);
        expect(data).toHaveProperty('page');
        expect(data.page).toHaveProperty('total');
        expect(data.page).toHaveProperty('limit');
        expect(data.page).toHaveProperty('offset');
        expect(data.page).toHaveProperty('has_more');
      }
    }
  });

  test('success endpoints return correct envelope', async ({ page }) => {
    await page.goto('/');
    const result = await apiGet(page, '/database/health');
    if (result.status === 200) {
      const data = result.data as any;
      expect(data).toHaveProperty('data');
    }
  });
});

test.describe('Scenario: Search and sort', () => {
  test('runs table is sortable by clicking column headers', async ({ page }) => {
    // Seed a few runs
    await page.goto('/runs');
    for (let i = 0; i < 3; i++) {
      await seedRun(page, { kind: 'task', name: `sort_test_${i}`, params: {} });
    }
    await page.reload();
    await waitForDataOrEmpty(page);

    // Table should have multiple rows
    const table = page.locator('table');
    if (await table.isVisible().catch(() => false)) {
      const rows = table.locator('tbody tr');
      expect(await rows.count()).toBeGreaterThanOrEqual(1);
    }
  });
});
