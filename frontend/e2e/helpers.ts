/**
 * Shared E2E test helpers for spine-core frontend.
 *
 * Provides API interaction utilities, wait helpers, and assertion utilities
 * that all test files can import.
 */
import { type Page, expect } from '@playwright/test';

// ── API Constants ──────────────────────────────────────────────────

export const DIRECT_API = process.env.API_URL || 'http://localhost:12000';
export const API_PREFIX = '/api/v1';

// ── API interaction helpers ────────────────────────────────────────

/** POST to an API endpoint via page's fetch context (uses proxy). */
export async function apiPost(page: Page, endpoint: string, body: unknown) {
  return page.evaluate(
    async ({ url, payload }) => {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      return { status: res.status, data: await res.json().catch(() => ({})) };
    },
    { url: `${API_PREFIX}${endpoint}`, payload: body },
  );
}

/** GET from an API endpoint via page's fetch context (uses proxy). */
export async function apiGet(page: Page, endpoint: string) {
  return page.evaluate(
    async ({ url }) => {
      const res = await fetch(url);
      return { status: res.status, data: await res.json().catch(() => ({})) };
    },
    { url: `${API_PREFIX}${endpoint}` },
  );
}

/** DELETE an API endpoint via page's fetch context. */
export async function apiDelete(page: Page, endpoint: string) {
  return page.evaluate(
    async ({ url }) => {
      const res = await fetch(url, { method: 'DELETE' });
      return { status: res.status, data: await res.json().catch(() => ({})) };
    },
    { url: `${API_PREFIX}${endpoint}` },
  );
}

/** PUT an API endpoint via page's fetch context. */
export async function apiPut(page: Page, endpoint: string, body: unknown) {
  return page.evaluate(
    async ({ url, payload }) => {
      const res = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      return { status: res.status, data: await res.json().catch(() => ({})) };
    },
    { url: `${API_PREFIX}${endpoint}`, payload: body },
  );
}

// ── Seed helpers ───────────────────────────────────────────────────

/** Seed a run via API and return the run_id. */
export async function seedRun(
  page: Page,
  body: Record<string, unknown> = { kind: 'task', name: 'e2e_test', params: {} },
): Promise<string | null> {
  const result = await apiPost(page, '/runs', body);
  return result.status === 202 ? (result.data as any)?.data?.run_id : null;
}

/** Ensure the database is initialized. */
export async function ensureDb(page: Page) {
  try {
    await page.request.post(`${DIRECT_API}/api/v1/database/init`);
  } catch {
    // Backend may not be running — tests handle gracefully
  }
}

// ── Wait helpers ───────────────────────────────────────────────────

/** Wait for any data display: table, empty state, error state, or grid. */
export async function waitForContent(page: Page, timeout = 8000) {
  await expect(
    page
      .locator('table, [data-testid], .text-center.py-12, .bg-red-50, .grid, main h2, main h3')
      .first(),
  ).toBeVisible({ timeout });
}

/** Wait for a page heading to be visible. */
export async function waitForHeading(page: Page, name: string | RegExp, timeout = 5000) {
  await expect(
    page.getByRole('heading', { name }).or(page.getByText(name).first()),
  ).toBeVisible({ timeout });
}

// ── Assertion helpers ──────────────────────────────────────────────

/** Assert a standard PagedResponse envelope. */
export function assertPagedEnvelope(body: Record<string, unknown>) {
  expect(body).toHaveProperty('data');
  expect(Array.isArray(body.data)).toBe(true);
  expect(body).toHaveProperty('page');
  const pg = body.page as Record<string, unknown>;
  expect(pg).toHaveProperty('total');
  expect(pg).toHaveProperty('limit');
  expect(pg).toHaveProperty('offset');
  expect(pg).toHaveProperty('has_more');
  expect(typeof pg.total).toBe('number');
}

/** Assert a standard SuccessResponse envelope. */
export function assertSuccessEnvelope(body: Record<string, unknown>) {
  expect(body).toHaveProperty('data');
  expect(typeof body.data).toBe('object');
}

/** Check if an element is visible, returning false on timeout. */
export async function isVisible(page: Page, locator: string, timeout = 2000): Promise<boolean> {
  return page.locator(locator).isVisible({ timeout }).catch(() => false);
}
