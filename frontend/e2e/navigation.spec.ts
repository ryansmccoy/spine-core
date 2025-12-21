import { test, expect } from '@playwright/test';

/**
 * Navigation & layout tests: verify the SPA chrome, sidebar,
 * and that every route renders without crashing.
 *
 * Covers all 11 nav items across 4 sections:
 *   OVERVIEW:   Dashboard
 *   EXECUTION:  Runs, Workflows, Schedules
 *   OPERATIONS: Dead Letters, Quality, Stats & Workers, Database
 *   DEVELOP:    Functions, Examples, Playground
 */

test.describe('Layout & Navigation', () => {
  test('renders the sidebar with all 11 nav links', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/dashboard/);

    const sidebar = page.locator('nav');
    await expect(sidebar).toBeVisible();

    // App title
    await expect(sidebar.getByText('spine-core')).toBeVisible();
    await expect(sidebar.getByText('execution engine')).toBeVisible();

    // All 11 nav items
    const expectedLinks = [
      'Dashboard',
      'Runs',
      'Workflows',
      'Schedules',
      'Dead Letters',
      'Quality',
      'Stats & Workers',
      'Database',
      'Functions',
      'Examples',
      'Playground',
    ];
    for (const label of expectedLinks) {
      await expect(sidebar.getByRole('link', { name: label })).toBeVisible();
    }
  });

  test('sidebar shows section headers', async ({ page }) => {
    await page.goto('/dashboard');
    const sidebar = page.locator('nav');

    // 4 section labels
    await expect(sidebar.getByText('OVERVIEW')).toBeVisible();
    await expect(sidebar.getByText('EXECUTION')).toBeVisible();
    await expect(sidebar.getByText('OPERATIONS')).toBeVisible();
    await expect(sidebar.getByText('DEVELOP')).toBeVisible();
  });

  test('root "/" redirects to /dashboard', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test('navigates to every page via sidebar', async ({ page }) => {
    await page.goto('/dashboard');

    const routes: Array<{ link: string; url: RegExp; heading: string | RegExp }> = [
      { link: 'Runs', url: /\/runs$/, heading: 'Execution Runs' },
      { link: 'Workflows', url: /\/workflows/, heading: 'Workflows' },
      { link: 'Schedules', url: /\/schedules/, heading: 'Schedules' },
      { link: 'Dead Letters', url: /\/dlq/, heading: 'Dead Letter Queue' },
      { link: 'Quality', url: /\/quality/, heading: /Quality/ },
      { link: 'Stats & Workers', url: /\/stats/, heading: /Stats/ },
      { link: 'Database', url: /\/database/, heading: 'Database' },
      { link: 'Functions', url: /\/functions/, heading: 'Functions' },
      { link: 'Examples', url: /\/examples/, heading: 'Examples' },
      { link: 'Playground', url: /\/playground/, heading: 'Playground' },
      { link: 'Dashboard', url: /\/dashboard/, heading: 'Dashboard' },
    ];

    for (const { link, url, heading } of routes) {
      await page.getByRole('link', { name: link }).click();
      await expect(page).toHaveURL(url);
      await expect(
        page.getByRole('heading', { name: heading }).or(page.getByText(heading).first())
      ).toBeVisible({ timeout: 5_000 });
    }
  });

  test('active nav item is highlighted', async ({ page }) => {
    await page.goto('/runs');
    const runsLink = page.locator('nav a[href="/runs"]');
    // Active class uses bg-spine-600/20
    await expect(runsLink).toHaveClass(/bg-spine/);

    const dashLink = page.locator('nav a[href="/dashboard"]');
    await expect(dashLink).not.toHaveClass(/bg-spine-6/);
  });

  test('sidebar collapse/expand toggle works', async ({ page }) => {
    await page.goto('/dashboard');

    const sidebar = page.locator('nav');
    // Initially expanded — labels visible
    await expect(sidebar.getByText('Dashboard')).toBeVisible();

    // Click collapse button
    const collapseBtn = sidebar.locator('button').filter({ has: page.locator('svg') }).last();
    await collapseBtn.click();

    // After collapse, text labels should be hidden
    // The nav should be narrow (w-16)
    await expect(sidebar).toHaveClass(/w-16/);

    // Click expand
    await collapseBtn.click();
    await expect(sidebar).toHaveClass(/w-60/);
  });

  test('breadcrumb shows current page', async ({ page }) => {
    await page.goto('/runs');
    const header = page.locator('header');
    await expect(header.getByText('spine')).toBeVisible();
    await expect(header.getByText('Runs')).toBeVisible();
  });

  test('breadcrumb shows nested path for detail pages', async ({ page }) => {
    await page.goto('/workflows/test-workflow');
    const header = page.locator('header');
    await expect(header.getByText('spine')).toBeVisible();
    // Should show Workflows as link and detail as text
    await expect(header.getByText('Workflows')).toBeVisible();
  });

  test('version badge shows in sidebar footer', async ({ page }) => {
    await page.goto('/dashboard');
    const sidebar = page.locator('nav');
    await expect(sidebar.getByText(/v\d+\.\d+\.\d+/)).toBeVisible();
    await expect(sidebar.getByText('API connected')).toBeVisible();
  });
});
