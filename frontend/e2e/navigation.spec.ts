import { test, expect } from '@playwright/test';

/**
 * Navigation & layout tests: verify the SPA chrome, sidebar,
 * and that every route renders without crashing.
 */

test.describe('Layout & Navigation', () => {
  test('renders the sidebar with all nav links', async ({ page }) => {
    await page.goto('/');
    // Should redirect to /dashboard
    await expect(page).toHaveURL(/\/dashboard/);

    const sidebar = page.locator('nav');
    await expect(sidebar).toBeVisible();

    // App title
    await expect(sidebar.getByText('spine-core')).toBeVisible();
    await expect(sidebar.getByText('execution dashboard')).toBeVisible();

    // All 7 nav items — use getByRole to avoid icon text conflicts
    const expectedLinks = [
      'Dashboard',
      'Runs',
      'Workflows',
      'Schedules',
      'Dead Letters',
      'Quality',
      'Stats & Workers',
    ];
    for (const label of expectedLinks) {
      await expect(sidebar.getByRole('link', { name: label })).toBeVisible();
    }
  });

  test('root "/" redirects to /dashboard', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test('navigates to each page via sidebar', async ({ page }) => {
    await page.goto('/dashboard');

    const routes: Array<{ link: string; url: RegExp; heading: string | RegExp }> = [
      { link: 'Runs', url: /\/runs$/, heading: 'Execution Runs' },
      { link: 'Workflows', url: /\/workflows/, heading: 'Workflows' },
      { link: 'Schedules', url: /\/schedules/, heading: 'Schedules' },
      { link: 'Dead Letters', url: /\/dlq/, heading: 'Dead Letter Queue' },
      { link: 'Quality', url: /\/quality/, heading: 'Quality & Anomalies' },
      { link: 'Stats & Workers', url: /\/stats/, heading: 'System Stats' },
      { link: 'Dashboard', url: /\/dashboard/, heading: 'Dashboard' },
    ];

    for (const { link, url, heading } of routes) {
      await page.getByRole('link', { name: link }).click();
      await expect(page).toHaveURL(url);
      await expect(
        page.getByRole('heading', { name: heading instanceof RegExp ? heading : heading })
      ).toBeVisible();
    }
  });

  test('active nav item is highlighted', async ({ page }) => {
    await page.goto('/runs');
    const runsLink = page.locator('nav a[href="/runs"]');
    await expect(runsLink).toHaveClass(/bg-spine-700/);

    const dashLink = page.locator('nav a[href="/dashboard"]');
    await expect(dashLink).not.toHaveClass(/bg-spine-700/);
  });
});
