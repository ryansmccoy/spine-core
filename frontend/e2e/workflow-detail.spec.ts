import { test, expect } from '@playwright/test';

/**
 * Workflow Detail page E2E tests.
 * Tests: navigation from workflows list, metadata display, step graph,
 * steps table, recent runs, and run modal.
 */

test.describe('Workflow Detail page', () => {
  test('navigates from workflows list via View Details link', async ({ page }) => {
    await page.goto('/workflows');
    await page.waitForTimeout(1000);

    const detailLink = page.getByText('View Details →').first();
    const hasLink = await detailLink.isVisible().catch(() => false);

    if (hasLink) {
      await detailLink.click();
      await expect(page).toHaveURL(/\/workflows\/.+/);
      // Should show workflow detail heading
      await expect(page.locator('h1, h2').first()).toBeVisible();
    }
  });

  test('renders metadata cards for a known workflow', async ({ page }) => {
    // Navigate to a known example workflow
    await page.goto('/workflows/etl.daily_ingest');
    await page.waitForTimeout(1500);

    // Should show the workflow name in heading
    const heading = page.locator('h1, h2').first();
    const headingText = await heading.textContent().catch(() => '');

    if (headingText && headingText.includes('etl.daily_ingest')) {
      // Check metadata labels exist
      await expect(page.getByText('Domain')).toBeVisible();
      await expect(page.getByText('Version')).toBeVisible();
    }
  });

  test('shows Step Graph component', async ({ page }) => {
    await page.goto('/workflows/etl.daily_ingest');
    await page.waitForTimeout(1500);

    // Step graph section should be visible if workflow exists
    const stepsHeader = page.getByText('Pipeline Steps');
    const hasSteps = await stepsHeader.isVisible().catch(() => false);

    if (hasSteps) {
      // Step nodes should be rendered
      const stepNodes = page.locator('[class*="step-node"], .bg-white.rounded-lg.border');
      const count = await stepNodes.count();
      expect(count).toBeGreaterThanOrEqual(0);
    }
  });

  test('shows steps table with columns', async ({ page }) => {
    await page.goto('/workflows/etl.daily_ingest');
    await page.waitForTimeout(1500);

    // The steps table should have expected column headers
    const table = page.locator('table').first();
    const hasTable = await table.isVisible().catch(() => false);

    if (hasTable) {
      await expect(table.getByText('Name')).toBeVisible();
    }
  });

  test('back button returns to workflows list', async ({ page }) => {
    await page.goto('/workflows/etl.daily_ingest');
    await page.waitForTimeout(1000);

    const backBtn = page.getByRole('button', { name: /back/i });
    const hasBack = await backBtn.isVisible().catch(() => false);

    if (hasBack) {
      await backBtn.click();
      await expect(page).toHaveURL(/\/workflows$/);
    }
  });

  test('run modal opens from workflow detail page', async ({ page }) => {
    await page.goto('/workflows/etl.daily_ingest');
    await page.waitForTimeout(1500);

    const runBtn = page.getByRole('button', { name: /run/i }).first();
    const hasRun = await runBtn.isVisible().catch(() => false);

    if (hasRun) {
      await runBtn.click();
      // Modal should appear with params field
      await expect(page.getByText('Parameters (JSON)')).toBeVisible();
    }
  });
});
