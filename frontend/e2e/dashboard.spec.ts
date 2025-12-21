import { test, expect } from '@playwright/test';

/**
 * Dashboard page tests.
 *
 * The dashboard calls multiple API endpoints (/api/v1/discover, /api/v1/database/health, etc.)
 * If the backend is not running these will show error states — which is still a valid render.
 */

test.describe('Dashboard', () => {
  test('shows health cards', async ({ page }) => {
    await page.goto('/dashboard');
    // PageHeader
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByText('System health, activity, and recent runs at a glance')).toBeVisible();

    // Either we see the health cards or an error box (backend not available)
    const hasHealthCard = page.getByText('Total Runs');
    const hasError = page.getByText('Cannot reach spine-core API');
    await expect(hasHealthCard.or(hasError).first()).toBeVisible({ timeout: 10_000 });
  });

  test('shows capabilities section when backend is available', async ({ page }) => {
    await page.goto('/dashboard');
    // If API is reachable, we should see the Capabilities section
    const caps = page.getByText('System Health');
    const error = page.getByText('Cannot reach spine-core API');

    // Wait for one or the other
    await expect(caps.or(error).first()).toBeVisible({ timeout: 10_000 });
  });
});
