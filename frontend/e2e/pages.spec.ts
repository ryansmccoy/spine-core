import { test, expect } from '@playwright/test';

/**
 * Tests for pages that present data lists from the API.
 * Each test validates the page renders correctly in both states:
 *   1. Empty/no-backend → shows empty-state or error
 *   2. With backend data → shows table/cards
 */

test.describe('Runs page', () => {
  test('renders heading and submit button', async ({ page }) => {
    await page.goto('/runs');
    const main = page.locator('main');
    await expect(main.getByRole('heading', { name: 'Runs' })).toBeVisible();

    // Submit button exists
    const submitBtn = page.getByRole('button', { name: /new run/i });
    await expect(submitBtn).toBeVisible();
  });

  test('submit dialog opens and closes', async ({ page }) => {
    await page.goto('/runs');
    await page.getByRole('button', { name: /new run/i }).click();

    // Dialog opens
    const dialog = page.locator('.fixed.inset-0');
    await expect(dialog.getByText('Submit New Run')).toBeVisible();
    await expect(page.getByLabel('Kind')).toBeVisible();
    await expect(page.getByLabel('Name')).toBeVisible();

    // Cancel closes dialog — scope to dialog to avoid matching table Cancel buttons
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog.getByText('Submit New Run')).not.toBeVisible();
  });
});

test.describe('Workflows page', () => {
  test('renders heading and shows empty or data', async ({ page }) => {
    await page.goto('/workflows');
    await expect(page.getByRole('heading', { name: 'Workflows' })).toBeVisible();
    await expect(
      page.getByText('Registered workflow definitions').or(
        page.getByText('No workflows registered')
      ).or(
        page.getByText('Failed to load workflows')
      ).first()
    ).toBeVisible({ timeout: 10_000 });
  });
});

test.describe('Schedules page', () => {
  test('renders heading and create button', async ({ page }) => {
    await page.goto('/schedules');
    await expect(page.getByRole('heading', { name: 'Schedules' })).toBeVisible();
    const createBtn = page.getByRole('button', { name: /new schedule/i });
    await expect(createBtn).toBeVisible();
  });

  test('create schedule dialog opens', async ({ page }) => {
    await page.goto('/schedules');
    await page.getByRole('button', { name: /new schedule/i }).click();
    await expect(page.getByText('Create Schedule')).toBeVisible();
    await expect(page.getByLabel('Workflow')).toBeVisible();
    await expect(page.getByLabel('Cron Expression')).toBeVisible();
  });
});

test.describe('DLQ page', () => {
  test('renders heading and shows empty or data', async ({ page }) => {
    await page.goto('/dlq');
    await expect(page.getByRole('heading', { name: 'Dead Letter Queue' })).toBeVisible();
    await expect(
      page.getByText('Failed items that exceeded retry limits')
    ).toBeVisible();

    // Either empty state or table with headers
    await expect(
      page.getByText('Dead letter queue is empty').or(
        page.getByText('Pipeline')
      ).or(
        page.getByText('Failed to load dead letters')
      ).first()
    ).toBeVisible({ timeout: 10_000 });
  });
});

test.describe('Quality page', () => {
  test('renders heading and both sections', async ({ page }) => {
    await page.goto('/quality');
    await expect(page.getByText('Quality & Anomalies')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Quality Results' })).toBeVisible();
  });
});

test.describe('Stats page', () => {
  test('renders heading and refresh button', async ({ page }) => {
    await page.goto('/stats');
    await expect(page.getByText('System Stats')).toBeVisible();
    const refreshBtn = page.getByRole('button', { name: /refresh/i });
    await expect(refreshBtn).toBeVisible();
  });

  test('shows execution counts section', async ({ page }) => {
    await page.goto('/stats');
    const main = page.locator('main');
    await expect(main.getByRole('heading', { name: 'Execution Counts' })).toBeVisible();
  });
});
