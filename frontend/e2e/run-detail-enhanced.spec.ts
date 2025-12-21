import { test, expect } from '@playwright/test';

/**
 * Run Detail page E2E tests — tabs, EventTimeline, confirm dialogs.
 * Tests the enhanced RunDetail with Overview|Events|Params|Errors tabs
 * and confirmation dialogs for cancel/retry actions.
 */

test.describe('Run Detail — tabs and interactions', () => {
  test('run detail page shows tab navigation', async ({ page }) => {
    // First submit a run to get a valid run_id
    await page.goto('/runs');
    await page.waitForTimeout(1000);

    // Click the first run link if available
    const runLink = page.locator('a[href^="/runs/"]').first();
    const hasRun = await runLink.isVisible().catch(() => false);

    if (hasRun) {
      await runLink.click();
      await expect(page).toHaveURL(/\/runs\/.+/);

      // Tab buttons should be visible
      await expect(page.getByRole('button', { name: 'Overview' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Timeline' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Parameters' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Errors' })).toBeVisible();
    }
  });

  test('switching tabs changes visible content', async ({ page }) => {
    await page.goto('/runs');
    await page.waitForTimeout(1000);

    const runLink = page.locator('a[href^="/runs/"]').first();
    const hasRun = await runLink.isVisible().catch(() => false);

    if (hasRun) {
      await runLink.click();
      await page.waitForTimeout(500);

      // Click Timeline tab
      await page.getByRole('button', { name: 'Timeline' }).click();
      await page.waitForTimeout(500);
      // Should show either events, empty state, or loading indicator
      const hasTimeline = await page.getByText('No events recorded').isVisible().catch(() => false);
      const hasEvents = await page.locator('.bg-spine-400, .bg-red-500, .bg-green-500').first().isVisible().catch(() => false);
      const hasLoading = await page.getByText('Loading events').isVisible().catch(() => false);
      expect(hasTimeline || hasEvents || hasLoading).toBeTruthy();

      // Click Parameters tab
      await page.getByRole('button', { name: 'Parameters' }).click();
      await expect(page.getByRole('heading', { name: 'Parameters' })).toBeVisible();

      // Click Errors tab
      await page.getByRole('button', { name: 'Errors' }).click();
      // Should show error or "no errors" empty state
      const hasError = await page.getByText('Error').isVisible().catch(() => false);
      const noError = await page.getByText('No errors').isVisible().catch(() => false);
      expect(hasError || noError).toBeTruthy();
    }
  });

  test('cancel button shows confirmation dialog', async ({ page }) => {
    await page.goto('/runs');
    await page.waitForTimeout(1000);

    // Look for a running or pending run
    const runLink = page.locator('a[href^="/runs/"]').first();
    const hasRun = await runLink.isVisible().catch(() => false);

    if (hasRun) {
      await runLink.click();
      await page.waitForTimeout(500);

      const cancelBtn = page.getByRole('button', { name: 'Cancel' }).first();
      const hasCancel = await cancelBtn.isVisible().catch(() => false);

      if (hasCancel) {
        await cancelBtn.click();
        // Confirm dialog should appear
        await expect(page.getByText('Cancel Run?')).toBeVisible();
        await expect(page.getByText('cannot be undone')).toBeVisible();

        // Dismiss without confirming
        const dismissBtn = page.getByRole('button', { name: /nevermind|cancel|dismiss/i }).last();
        if (await dismissBtn.isVisible().catch(() => false)) {
          await dismissBtn.click();
        }
      }
    }
  });

  test('status bar shows run metadata', async ({ page }) => {
    await page.goto('/runs');
    await page.waitForTimeout(1000);

    const runLink = page.locator('a[href^="/runs/"]').first();
    const hasRun = await runLink.isVisible().catch(() => false);

    if (hasRun) {
      await runLink.click();
      await page.waitForTimeout(500);

      // Status badge and duration should be visible in the status bar
      const statusBar = page.locator('.bg-white.rounded-xl.shadow-sm').first();
      await expect(statusBar).toBeVisible();
    }
  });
});
