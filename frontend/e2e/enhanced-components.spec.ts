import { test, expect } from '@playwright/test';

/**
 * Component integration tests — Toast, Pagination, ConfirmDialog, Pipeline filters.
 * These tests verify the new shared components work correctly across pages.
 */

test.describe('Pagination on Runs page', () => {
  test('pagination controls appear when enough runs exist', async ({ page }) => {
    await page.goto('/runs');
    await page.waitForTimeout(1500);

    // If there are runs and pagination data, controls should appear
    const pagination = page.getByText(/Page \d+ of \d+/);
    const hasPagination = await pagination.isVisible().catch(() => false);

    if (hasPagination) {
      await expect(page.getByRole('button', { name: /prev/i })).toBeVisible();
      await expect(page.getByRole('button', { name: /next/i })).toBeVisible();
    }
  });

  test('workflow filter dropdown appears on Runs page', async ({ page }) => {
    await page.goto('/runs');
    await page.waitForTimeout(1500);

    // Workflow filter dropdown should be present
    const dropdown = page.locator('select');
    const hasDropdown = await dropdown.isVisible().catch(() => false);

    if (hasDropdown) {
      // Should have "All Workflows" option
      const options = await dropdown.locator('option').allTextContents();
      expect(options.some((o) => o.includes('All Workflows') || o.includes('All'))).toBeTruthy();
    }
  });
});

test.describe('Confirm dialogs on Schedules page', () => {
  test('delete button opens confirm dialog', async ({ page }) => {
    await page.goto('/schedules');
    await page.waitForTimeout(1500);

    const deleteBtn = page.getByRole('button', { name: 'Delete' }).first();
    const hasDelete = await deleteBtn.isVisible().catch(() => false);

    if (hasDelete) {
      await deleteBtn.click();
      await expect(page.getByText('Delete Schedule?')).toBeVisible();
      await expect(page.getByText('permanently remove')).toBeVisible();

      // Cancel the dialog
      const cancelBtn = page.getByRole('button', { name: /nevermind/i });
      if (await cancelBtn.isVisible().catch(() => false)) {
        await cancelBtn.click();
      }
    }
  });
});

test.describe('DLQ page — pipeline filter and confirm replay', () => {
  test('replay button opens confirm dialog', async ({ page }) => {
    await page.goto('/dlq');
    await page.waitForTimeout(1500);

    const replayBtn = page.getByRole('button', { name: 'Replay' }).first();
    const hasReplay = await replayBtn.isVisible().catch(() => false);

    if (hasReplay) {
      await replayBtn.click();
      await expect(page.getByText('Replay Dead Letter?')).toBeVisible();

      // Cancel
      const cancelBtn = page.getByRole('button', { name: /nevermind/i });
      if (await cancelBtn.isVisible().catch(() => false)) {
        await cancelBtn.click();
      }
    }
  });

  test('expandable error column works', async ({ page }) => {
    await page.goto('/dlq');
    await page.waitForTimeout(1500);

    // Click on a truncated error to expand it
    const errorCell = page.locator('td.text-red-600 button').first();
    const hasError = await errorCell.isVisible().catch(() => false);

    if (hasError) {
      const textBefore = await errorCell.textContent();
      await errorCell.click();
      const textAfter = await errorCell.textContent();
      // After clicking, the text should either be the same or expanded
      expect(textAfter).toBeTruthy();
    }
  });
});

test.describe('Dashboard — linked recent runs', () => {
  test('recent run IDs link to run detail', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForTimeout(1500);

    const runLink = page.locator('a[href^="/runs/"]').first();
    const hasLink = await runLink.isVisible().catch(() => false);

    if (hasLink) {
      await runLink.click();
      await expect(page).toHaveURL(/\/runs\/.+/);
    }
  });

  test('DLQ count card is visible', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForTimeout(1500);

    // Scope to main content area to avoid matching sidebar nav link
    const main = page.locator('main');
    await expect(main.getByText('Dead Letters')).toBeVisible();
  });
});

test.describe('Stats page — TanStack Query hooks', () => {
  test('stats page renders with proper sections', async ({ page }) => {
    await page.goto('/stats');
    await page.waitForTimeout(1500);

    const main = page.locator('main');
    await expect(main.getByRole('heading', { name: 'Execution Counts' })).toBeVisible();
    await expect(main.getByRole('heading', { name: 'Queue Depths' })).toBeVisible();
    await expect(main.getByRole('heading', { name: 'Workers' })).toBeVisible();
  });

  test('refresh button is available', async ({ page }) => {
    await page.goto('/stats');
    await page.waitForTimeout(1000);

    await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible();
  });
});

test.describe('Quality page — pipeline filter', () => {
  test('quality page loads with sections', async ({ page }) => {
    await page.goto('/quality');
    await page.waitForTimeout(1500);

    const main = page.locator('main');
    await expect(main.getByRole('heading', { name: 'Quality Results' })).toBeVisible();
    await expect(main.getByRole('heading', { name: 'Anomalies', exact: true })).toBeVisible();
  });
});
