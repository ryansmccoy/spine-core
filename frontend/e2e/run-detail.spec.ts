import { test, expect } from '@playwright/test';

/**
 * Tests for RunDetail page /runs/:runId
 *
 * The page shows run metadata, timeline events, and action buttons.
 * Tests handle both error state (run not found) and success state.
 */

test.describe('RunDetail page', () => {
  test('shows error state for non-existent run', async ({ page }) => {
    // Navigate to a fake run ID
    await page.goto('/runs/fake-run-id-12345');

    // Should show error message (run not found)
    await expect(
      page.getByText('Run not found').or(page.getByText('No data')).first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test('back button navigates to runs list from error state', async ({ page }) => {
    await page.goto('/runs/fake-run-id-12345');

    // Even in error state, if a back button exists, it should work
    const backBtn = page.getByRole('button', { name: /back/i });
    if (await backBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await backBtn.click();
      await expect(page).toHaveURL('/runs');
    }
  });

  test('run detail page renders with correct structure from runs list', async ({
    page,
  }) => {
    // Go to runs page first
    await page.goto('/runs');
    await expect(page.getByRole('heading', { name: 'Execution Runs' })).toBeVisible();

    // If there's a run link, click on it to navigate to detail
    const runLink = page.locator('a[href*="/runs/"]').first();
    if (await runLink.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await runLink.click();

      // Verify we're on run detail page (URL contains /runs/)
      await expect(page).toHaveURL(/\/runs\/.+/);

      // Check structure elements that should always be present
      const backBtn = page.getByRole('button', { name: /back/i });
      await expect(backBtn).toBeVisible();

      // Status badge should exist
      await expect(page.getByText(/Status/i).first()).toBeVisible();

      // Event history section should exist
      await expect(page.getByText('Event History')).toBeVisible();
    }
  });

  test('cancel button appears for running status', async ({ page }) => {
    // Navigate to runs list
    await page.goto('/runs');

    // Look for a run with "running" or "pending" status
    const runningRow = page
      .locator('tr')
      .filter({ hasText: /running|pending/i })
      .first();

    if (await runningRow.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await runningRow.click();
      await expect(page).toHaveURL(/\/runs\/.+/);

      // Cancel button should be visible for non-terminal runs
      const cancelBtn = page.getByRole('button', { name: /cancel/i });
      await expect(cancelBtn).toBeVisible();
    }
  });

  test('retry button appears for failed status', async ({ page }) => {
    await page.goto('/runs');

    // Look for a run with "failed" status
    const failedRow = page
      .locator('tr')
      .filter({ hasText: /failed|dead_lettered/i })
      .first();

    if (await failedRow.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await failedRow.click();
      await expect(page).toHaveURL(/\/runs\/.+/);

      // Retry button should be visible for failed runs
      const retryBtn = page.getByRole('button', { name: /retry/i });
      await expect(retryBtn).toBeVisible();
    }
  });
});
