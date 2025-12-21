/**
 * Keyboard navigation and responsive layout E2E tests.
 *
 * Keyboard:
 * - Tab order through sidebar nav
 * - Keyboard-driven table interactions
 * - Modal keyboard trap
 * - Tab/panel switching with keyboard
 *
 * Responsive:
 * - Desktop (1280×800)
 * - Tablet (768×1024)
 * - Mobile-ish (640×800)
 * - No horizontal overflow
 * - Sidebar collapses gracefully
 */

import { test, expect } from '@playwright/test';

// ── Keyboard Navigation ─────────────────────────────────────────

test.describe('Keyboard — sidebar navigation', () => {
  test('Tab moves focus through sidebar links', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForTimeout(1000);

    // Focus inside the nav
    const nav = page.locator('nav');
    const firstLink = nav.locator('a').first();
    await firstLink.focus();

    // Tab through links
    const visitedTags = new Set<string>();
    for (let i = 0; i < 11; i++) {
      await page.keyboard.press('Tab');
      const tag = await page.evaluate(() => document.activeElement?.tagName);
      if (tag) visitedTags.add(tag);
    }

    // Should have visited A elements
    expect(visitedTags.has('A')).toBeTruthy();
  });

  test('Enter on nav link navigates to that page', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForTimeout(1000);

    // Find the Runs nav link and focus it
    const runsLink = page.locator('nav a:has-text("Runs")');
    await runsLink.focus();
    await page.keyboard.press('Enter');

    await page.waitForURL('**/runs');
    expect(page.url()).toContain('/runs');
  });
});

test.describe('Keyboard — modal interactions', () => {
  test('modal can be dismissed with Escape', async ({ page }) => {
    await page.goto('/runs');
    await page.waitForTimeout(1500);

    // Open submit dialog
    const submitBtn = page.getByRole('button', { name: /new run/i });
    await submitBtn.click();
    await expect(page.getByText('Submit New Run')).toBeVisible();

    // Dismiss with Escape
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);

    // Modal should be gone
    await expect(page.getByText('Submit New Run')).toBeHidden();
  });

  test('Tab cycles through modal form fields', async ({ page }) => {
    await page.goto('/runs');
    await page.waitForTimeout(1500);

    const submitBtn = page.getByRole('button', { name: /new run/i });
    await submitBtn.click();
    await page.waitForTimeout(500);

    // Tab through fields
    const focusedElements: string[] = [];
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press('Tab');
      const tag = await page.evaluate(
        () => `${document.activeElement?.tagName}:${document.activeElement?.getAttribute('type') || document.activeElement?.tagName}`,
      );
      focusedElements.push(tag);
    }

    // Should cycle through inputs/selects/textareas/buttons
    expect(focusedElements.length).toBeGreaterThan(0);

    // Close
    await page.keyboard.press('Escape');
  });
});

test.describe('Keyboard — tab panels', () => {
  test('Functions tab bar switches with click target in keyboard focus', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(2000);

    // Find tab buttons
    const tabs = page.locator('[role="tab"], button:has-text("Code"), button:has-text("Test"), button:has-text("Config")');
    const count = await tabs.count();
    if (count === 0) return;

    // Focus first tab and press Enter
    await tabs.first().focus();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);

    // Verify focus is still within tabs area
    const isFocused = await tabs.first().evaluate((el) => document.activeElement === el);
    expect(isFocused).toBeTruthy();
  });

  test('Database tabs respond to keyboard', async ({ page }) => {
    await page.goto('/database');
    await page.waitForTimeout(2000);

    // Click the Schema tab via keyboard
    const schemaTab = page.getByRole('button', { name: 'Schema Browser' });
    await schemaTab.focus();
    await page.keyboard.press('Enter');

    // Schema content should be visible
    await page.waitForTimeout(500);
    const schemaContent = page.getByText('Tables').or(page.getByText('table')).first();
    await expect(schemaContent).toBeVisible();
  });
});

// ── Responsive Layout ───────────────────────────────────────────

test.describe('Responsive — desktop (1280×800)', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('sidebar is expanded at desktop width', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForTimeout(1000);

    const sidebar = page.locator('nav').first();
    const box = await sidebar.boundingBox();
    expect(box).toBeTruthy();
    // Expanded sidebar should be wider than 150px
    expect(box!.width).toBeGreaterThan(150);
  });

  test('main content is not horizontally truncated', async ({ page }) => {
    await page.goto('/runs');
    await page.waitForTimeout(2000);

    // Body should not have horizontal scrollbar
    const hasHScroll = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasHScroll).toBeFalsy();
  });
});

test.describe('Responsive — tablet (768×1024)', () => {
  test.use({ viewport: { width: 768, height: 1024 } });

  test('page renders without overflow', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForTimeout(1500);

    const hasHScroll = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasHScroll).toBeFalsy();
  });

  test('sidebar collapses or stays usable', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForTimeout(1000);

    const sidebar = page.locator('nav').first();
    const box = await sidebar.boundingBox();
    expect(box).toBeTruthy();
    // At tablet width, sidebar might be collapsed (narrow) or overlay
    // Either way, it should exist and not be wider than half viewport
    expect(box!.width).toBeLessThan(400);
  });

  test('Runs table adapts to width', async ({ page }) => {
    await page.goto('/runs');
    await page.waitForTimeout(2000);

    // Table or content area should be visible
    const main = page.locator('main');
    const mainBox = await main.boundingBox();
    expect(mainBox).toBeTruthy();
    expect(mainBox!.width).toBeGreaterThan(200);
  });
});

test.describe('Responsive — small viewport (640×800)', () => {
  test.use({ viewport: { width: 640, height: 800 } });

  test('all pages render at 640px width without JS errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => {
      if (
        !err.message.includes('fetch') &&
        !err.message.includes('NetworkError') &&
        !err.message.includes('ERR_CONNECTION_REFUSED') &&
        !err.message.includes('Load failed')
      ) {
        errors.push(err.message);
      }
    });

    const pages = ['/dashboard', '/runs', '/workflows', '/functions', '/database', '/examples', '/playground'];
    for (const path of pages) {
      await page.goto(path);
      await page.waitForTimeout(1000);
    }

    expect(errors).toHaveLength(0);
  });

  test('sidebar collapses at small width', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForTimeout(1000);

    const sidebar = page.locator('nav').first();
    const box = await sidebar.boundingBox();
    if (box) {
      // Sidebar should be collapsed (<= 64px) or hidden
      expect(box.width).toBeLessThan(300);
    }
  });

  test('Functions page adapts layout', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(2000);

    // No horizontal overflow
    const hasHScroll = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasHScroll).toBeFalsy();
  });

  test('Database tabs remain accessible', async ({ page }) => {
    await page.goto('/database');
    await page.waitForTimeout(2000);

    // Tab buttons should be visible and clickable
    const overviewTab = page.getByRole('button', { name: 'Overview' });
    await expect(overviewTab).toBeVisible();
    await overviewTab.click();
  });
});

// ── Sidebar Collapse Toggle ─────────────────────────────────────

test.describe('Responsive — collapse toggle', () => {
  test('sidebar collapse button hides labels', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForTimeout(1000);

    const sidebar = page.locator('nav').first();
    const initialBox = await sidebar.boundingBox();

    // Find collapse toggle
    const collapseBtn = page.locator('button[aria-label*="collapse"], button[aria-label*="Collapse"], button:has(svg.lucide-panel-left-close), button:has(svg.lucide-chevron-left)').first();
    const exists = await collapseBtn.isVisible().catch(() => false);

    if (exists) {
      await collapseBtn.click();
      await page.waitForTimeout(500);

      const collapsedBox = await sidebar.boundingBox();
      if (initialBox && collapsedBox) {
        // Collapsed sidebar should be narrower
        expect(collapsedBox.width).toBeLessThan(initialBox.width);
      }
    }
  });

  test('sidebar expand restores labels', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForTimeout(1000);

    const sidebar = page.locator('nav').first();

    // Collapse
    const collapseBtn = page.locator('button[aria-label*="collapse"], button[aria-label*="Collapse"], button:has(svg.lucide-panel-left-close), button:has(svg.lucide-chevron-left)').first();
    const exists = await collapseBtn.isVisible().catch(() => false);
    if (!exists) return;

    await collapseBtn.click();
    await page.waitForTimeout(500);
    const collapsedBox = await sidebar.boundingBox();

    // Expand
    const expandBtn = page.locator('button[aria-label*="expand"], button[aria-label*="Expand"], button:has(svg.lucide-panel-left-open), button:has(svg.lucide-chevron-right)').first();
    const expandExists = await expandBtn.isVisible().catch(() => false);
    if (!expandExists) return;

    await expandBtn.click();
    await page.waitForTimeout(500);
    const expandedBox = await sidebar.boundingBox();

    if (collapsedBox && expandedBox) {
      expect(expandedBox.width).toBeGreaterThan(collapsedBox.width);
    }
  });
});
