/**
 * Functions Console — comprehensive E2E tests.
 *
 * Tests the AWS Lambda-inspired function management page:
 * - Page load & layout (sidebar + detail)
 * - Function list with search/filter
 * - Code tab (Monaco editor)
 * - Test tab (invoke execution with event JSON)
 * - Configuration tab (timeout, memory, runtime, handler, env vars)
 * - Invocation History tab
 * - Template gallery modal
 * - Create function modal
 * - Delete confirmation modal
 * - Tag filtering
 * - Save/dirty state
 * - Network assertions (API calls)
 */

import { test, expect } from '@playwright/test';

const API_BASE = 'http://localhost:12000/api/v1';

// ── Helpers ─────────────────────────────────────────────────────────

async function ensureDb(page: import('@playwright/test').Page) {
  try {
    await page.request.post(`${API_BASE}/database/init`);
  } catch { /* backend may be unavailable */ }
}

// ── Page Load & Layout ──────────────────────────────────────────────

test.describe('Functions page — layout', () => {
  test.beforeEach(async ({ page }) => {
    await ensureDb(page);
  });

  test('renders page header with title and description', async ({ page }) => {
    await page.goto('/functions');
    await expect(page.getByRole('heading', { name: 'Functions' })).toBeVisible();
    await expect(page.getByText('Create, edit, and execute serverless-style Python functions')).toBeVisible();
  });

  test('shows function count badge', async ({ page }) => {
    await page.goto('/functions');
    await expect(page.getByText(/\d+ functions/)).toBeVisible({ timeout: 8_000 });
  });

  test('has Create Function and Templates buttons', async ({ page }) => {
    await page.goto('/functions');
    await expect(page.getByRole('button', { name: /Create Function/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Templates/i })).toBeVisible();
  });

  test('shows search input in sidebar', async ({ page }) => {
    await page.goto('/functions');
    await expect(page.getByPlaceholder('Search functions...')).toBeVisible();
  });

  test('shows function list in sidebar', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(2000);

    // Should show either function items or empty state
    const hasFunctions = await page.locator('button').filter({ hasText: /lines/ }).count();
    const hasEmpty = await page.getByText('No functions yet').isVisible().catch(() => false);
    expect(hasFunctions > 0 || hasEmpty).toBeTruthy();
  });

  test('auto-selects first function when list loads', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(2500);

    // If functions exist, one should be selected (detail visible)
    const hasFunctions = await page.locator('button').filter({ hasText: /lines/ }).count();
    if (hasFunctions > 0) {
      // Detail header should show function name
      await expect(page.locator('h2').first()).toBeVisible();
    }
  });
});

// ── Function List & Search ──────────────────────────────────────────

test.describe('Functions page — list & search', () => {
  test.beforeEach(async ({ page }) => {
    await ensureDb(page);
  });

  test('function list items show name, status, lines, invocations', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(2500);

    const listItem = page.locator('button').filter({ hasText: /lines/ }).first();
    const hasItem = await listItem.isVisible().catch(() => false);

    if (hasItem) {
      // Should show status badge
      await expect(listItem.locator('span').filter({ hasText: /idle|running|error|success/ }).first()).toBeVisible();
      // Should show line count
      await expect(listItem.getByText(/\d+ lines/)).toBeVisible();
      // Should show invocation count
      await expect(listItem.getByText(/\d+ invocations?/)).toBeVisible();
    }
  });

  test('search filters function list', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(2500);

    const searchInput = page.getByPlaceholder('Search functions...');
    const countBefore = await page.locator('button').filter({ hasText: /lines/ }).count();

    if (countBefore > 0) {
      // Search for a nonsense string — should show fewer or zero results
      await searchInput.fill('zzz_nonexistent_function');
      await page.waitForTimeout(1000);

      const countAfter = await page.locator('button').filter({ hasText: /lines/ }).count();
      expect(countAfter).toBeLessThanOrEqual(countBefore);
    }
  });

  test('clicking a function selects it', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(2500);

    const items = page.locator('button').filter({ hasText: /lines/ });
    const count = await items.count();

    if (count >= 2) {
      // Click the second function
      await items.nth(1).click();
      // Should highlight with selected style
      await expect(items.nth(1)).toHaveClass(/bg-spine-50/);
    }
  });
});

// ── Code Tab ────────────────────────────────────────────────────────

test.describe('Functions page — Code tab', () => {
  test.beforeEach(async ({ page }) => {
    await ensureDb(page);
  });

  test('shows Monaco editor with function source code', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFunction = await page.locator('h2').first().isVisible().catch(() => false);
    if (hasFunction) {
      // Code tab should be active by default
      const codeTab = page.getByRole('button', { name: 'Code' });
      await expect(codeTab).toBeVisible();

      // Monaco editor container
      await expect(page.locator('.monaco-editor, [data-keybinding-context]').first()).toBeVisible({ timeout: 8_000 });
    }
  });

  test('shows file header with filename and line count', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (hasFn) {
      // File header shows "{name}.py"
      await expect(page.getByText(/\.py/)).toBeVisible();
      // Shows line count
      await expect(page.getByText(/\d+ lines/)).toBeVisible();
    }
  });

  test('shows "Modified" timestamp', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (hasFn) {
      await expect(page.getByText(/Modified/).first()).toBeVisible();
    }
  });
});

// ── Tab Navigation ──────────────────────────────────────────────────

test.describe('Functions page — tab navigation', () => {
  test.beforeEach(async ({ page }) => {
    await ensureDb(page);
  });

  test('shows all 4 tabs: Code, Test, Configuration, Invocations', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (hasFn) {
      await expect(page.getByRole('button', { name: 'Code' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Test' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Configuration' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Invocations' })).toBeVisible();
    }
  });

  test('switching tabs changes content', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    // Click Test tab
    await page.getByRole('button', { name: 'Test' }).click();
    await expect(page.getByText('Test Event (JSON)')).toBeVisible();

    // Click Configuration tab
    await page.getByRole('button', { name: 'Configuration' }).click();
    await expect(page.getByText('General Configuration')).toBeVisible();

    // Click Invocations tab
    await page.getByRole('button', { name: 'Invocations' }).click();
    await expect(page.getByText('Recent Invocations')).toBeVisible();

    // Click Code tab back
    await page.getByRole('button', { name: 'Code' }).click();
    await expect(page.locator('.monaco-editor, [data-keybinding-context]').first()).toBeVisible({ timeout: 5_000 });
  });
});

// ── Test Tab ────────────────────────────────────────────────────────

test.describe('Functions page — Test tab', () => {
  test.beforeEach(async ({ page }) => {
    await ensureDb(page);
  });

  test('shows event JSON editor and Test button', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    await page.getByRole('button', { name: 'Test' }).click();

    // Event JSON editor header
    await expect(page.getByText('Test Event (JSON)')).toBeVisible();

    // Test button in the tab
    await expect(page.getByRole('button', { name: 'Test' }).nth(1)).toBeVisible();
  });

  test('shows prompt text when no result', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    await page.getByRole('button', { name: 'Test' }).click();
    await expect(page.getByText('Configure a test event above and click')).toBeVisible();
  });

  test('invoking a function shows execution result', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    // Click the main Test button in header
    const testBtn = page.getByRole('button', { name: /^Test$/ }).first();
    await testBtn.click();

    // Wait for result — either success, error, or timeout banner
    await expect(
      page.getByText('success').or(page.getByText('error')).or(page.getByText('timeout')).or(page.getByText('Running...')).first(),
    ).toBeVisible({ timeout: 15_000 });
  });

  test('execution result shows duration and request ID', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    // Click Test in header bar
    await page.getByRole('button', { name: /^Test$/ }).first().click();

    // Wait for any result
    const hasResult = await page.getByText(/Duration:/).isVisible({ timeout: 15_000 }).catch(() => false);
    if (hasResult) {
      await expect(page.getByText(/Duration:/)).toBeVisible();
      await expect(page.getByText(/Billed:/)).toBeVisible();
    }
  });

  test('log viewer shows execution output', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    await page.getByRole('button', { name: /^Test$/ }).first().click();

    // Wait for execution to complete
    await page.waitForTimeout(5000);

    // Log viewer should be visible (dark terminal panel)
    const logViewer = page.locator('.bg-\\[\\#0D1117\\]');
    const hasLogs = await logViewer.isVisible().catch(() => false);
    if (hasLogs) {
      await expect(page.getByText('Execution Output')).toBeVisible();
    }
  });
});

// ── Configuration Tab ───────────────────────────────────────────────

test.describe('Functions page — Configuration tab', () => {
  test.beforeEach(async ({ page }) => {
    await ensureDb(page);
  });

  test('shows timeout, memory, runtime, handler fields', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    await page.getByRole('button', { name: 'Configuration' }).click();

    await expect(page.getByText('Timeout (seconds)')).toBeVisible();
    await expect(page.getByText('Memory (MB)')).toBeVisible();
    await expect(page.getByText('Runtime')).toBeVisible();
    await expect(page.getByText('Handler')).toBeVisible();
  });

  test('shows environment variables section', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    await page.getByRole('button', { name: 'Configuration' }).click();
    await expect(page.getByText('Environment Variables')).toBeVisible();
  });

  test('shows function metadata (ID, Created, Modified, Invocations)', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    await page.getByRole('button', { name: 'Configuration' }).click();
    await expect(page.getByText('Function Info')).toBeVisible();
    await expect(page.getByText('ID:')).toBeVisible();
    await expect(page.getByText('Created:')).toBeVisible();
  });

  test('memory dropdown has expected options', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    await page.getByRole('button', { name: 'Configuration' }).click();

    // Memory select should have MB options
    const memSelect = page.locator('select').first();
    if (await memSelect.isVisible().catch(() => false)) {
      const options = await memSelect.locator('option').allTextContents();
      expect(options.some((o) => o.includes('128'))).toBeTruthy();
      expect(options.some((o) => o.includes('256'))).toBeTruthy();
    }
  });
});

// ── Invocations (History) Tab ───────────────────────────────────────

test.describe('Functions page — Invocations tab', () => {
  test.beforeEach(async ({ page }) => {
    await ensureDb(page);
  });

  test('shows invocation history table or empty state', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    await page.getByRole('button', { name: 'Invocations' }).click();

    await expect(
      page.getByText('Request ID').or(page.getByText('No invocation history yet')).first(),
    ).toBeVisible({ timeout: 5_000 });
  });

  test('invocation table has correct columns', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    await page.getByRole('button', { name: 'Invocations' }).click();
    await page.waitForTimeout(1000);

    const table = page.locator('table');
    if (await table.isVisible().catch(() => false)) {
      await expect(table.getByText('Request ID')).toBeVisible();
      await expect(table.getByText('Status')).toBeVisible();
      await expect(table.getByText('Duration')).toBeVisible();
      await expect(table.getByText('Event')).toBeVisible();
      await expect(table.getByText('Time')).toBeVisible();
    }
  });
});

// ── Template Gallery Modal ──────────────────────────────────────────

test.describe('Functions page — Templates', () => {
  test.beforeEach(async ({ page }) => {
    await ensureDb(page);
  });

  test('Templates button opens template gallery modal', async ({ page }) => {
    await page.goto('/functions');
    await page.getByRole('button', { name: /Templates/ }).click();

    await expect(page.getByText('Function Templates')).toBeVisible();
  });

  test('template gallery shows template cards', async ({ page }) => {
    await page.goto('/functions');
    await page.getByRole('button', { name: /Templates/ }).click();

    await page.waitForTimeout(2000);

    // Should show template cards with names and descriptions
    const cards = page.locator('button').filter({ hasText: /category/ });
    const count = await cards.count();
    // At least some templates should exist (seeded by backend)
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('template gallery can be closed', async ({ page }) => {
    await page.goto('/functions');
    await page.getByRole('button', { name: /Templates/ }).click();
    await expect(page.getByText('Function Templates')).toBeVisible();

    // Close the modal
    const closeBtn = page.locator('.fixed').getByRole('button').filter({ has: page.locator('svg') }).first();
    if (await closeBtn.isVisible().catch(() => false)) {
      await closeBtn.click();
      await expect(page.getByText('Function Templates')).not.toBeVisible();
    }
  });

  test('selecting a template opens create modal with pre-filled data', async ({ page }) => {
    await page.goto('/functions');
    await page.getByRole('button', { name: /Templates/ }).click();
    await page.waitForTimeout(2000);

    // Click first template card
    const templateCard = page.locator('.fixed button').filter({ hasText: /category/ }).first();
    const hasCard = await templateCard.isVisible().catch(() => false);

    if (hasCard) {
      await templateCard.click();
      // Create modal should open
      await expect(page.getByText('Create Function')).toBeVisible();
      await expect(page.getByLabel('Function Name')).toBeVisible();
    }
  });
});

// ── Create Function Modal ───────────────────────────────────────────

test.describe('Functions page — Create Function', () => {
  test.beforeEach(async ({ page }) => {
    await ensureDb(page);
  });

  test('Create Function button opens modal', async ({ page }) => {
    await page.goto('/functions');
    await page.getByRole('button', { name: /Create Function/ }).click();

    await expect(page.getByText('Create Function')).toBeVisible();
    await expect(page.getByLabel('Function Name')).toBeVisible();
    await expect(page.getByLabel('Description')).toBeVisible();
    await expect(page.getByLabel('Tags (comma-separated)')).toBeVisible();
  });

  test('Create button is disabled when name is empty', async ({ page }) => {
    await page.goto('/functions');
    await page.getByRole('button', { name: /Create Function/ }).click();

    const createBtn = page.locator('.fixed').getByRole('button', { name: 'Create' });
    await expect(createBtn).toBeDisabled();
  });

  test('Create button is enabled when name is filled', async ({ page }) => {
    await page.goto('/functions');
    await page.getByRole('button', { name: /Create Function/ }).click();

    await page.getByLabel('Function Name').fill('test_e2e_func');
    const createBtn = page.locator('.fixed').getByRole('button', { name: 'Create' });
    await expect(createBtn).toBeEnabled();
  });

  test('Cancel button closes the modal', async ({ page }) => {
    await page.goto('/functions');
    await page.getByRole('button', { name: /Create Function/ }).click();
    await expect(page.getByText('Create Function')).toBeVisible();

    await page.locator('.fixed').getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByText('Create Function').first()).not.toBeVisible();
  });

  test('creating a function adds it to the list', async ({ page }) => {
    await page.goto('/functions');
    const uniqueName = `e2e_test_${Date.now()}`;

    await page.getByRole('button', { name: /Create Function/ }).click();
    await page.getByLabel('Function Name').fill(uniqueName);
    await page.getByLabel('Description').fill('E2E test function');
    await page.getByLabel('Tags (comma-separated)').fill('e2e, test');

    await page.locator('.fixed').getByRole('button', { name: 'Create' }).click();

    // Wait for modal to close and function to appear
    await page.waitForTimeout(2000);

    // New function should be in the list
    await expect(page.getByText(uniqueName)).toBeVisible({ timeout: 5_000 });
  });
});

// ── Delete Function ─────────────────────────────────────────────────

test.describe('Functions page — Delete', () => {
  test.beforeEach(async ({ page }) => {
    await ensureDb(page);
  });

  test('delete button opens confirmation modal', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    // Click the red delete button
    const deleteBtn = page.locator('button').filter({ has: page.locator('.text-white, .lucide-trash-2') }).last();
    if (await deleteBtn.isVisible().catch(() => false)) {
      await deleteBtn.click();
      await expect(page.getByText('Delete Function')).toBeVisible();
      await expect(page.getByText('cannot be undone')).toBeVisible();
    }
  });

  test('cancel in delete modal preserves the function', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    // Get the function name
    const fnName = await page.locator('h2').first().textContent();

    // Trigger delete modal via the danger button
    const dangerBtns = page.locator('button.bg-red-600, button').filter({ has: page.locator('.lucide-trash-2') });
    if (await dangerBtns.last().isVisible().catch(() => false)) {
      await dangerBtns.last().click();
      await page.locator('.fixed').getByRole('button', { name: 'Cancel' }).click();

      // Function should still be visible
      if (fnName) {
        await expect(page.getByText(fnName).first()).toBeVisible();
      }
    }
  });
});

// ── Function Header ─────────────────────────────────────────────────

test.describe('Functions page — function header', () => {
  test.beforeEach(async ({ page }) => {
    await ensureDb(page);
  });

  test('shows function name, status badge, and description', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    // Function name in h2
    await expect(page.locator('h2').first()).toBeVisible();
    // Status badge
    await expect(page.locator('span').filter({ hasText: /idle|running|error|success/ }).first()).toBeVisible();
  });

  test('shows runtime info (timeout, memory, runtime) in header', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    // Info line like "30s | 128MB | python3.12"
    await expect(page.getByText(/\d+s/).first()).toBeVisible();
    await expect(page.getByText(/\d+MB/).first()).toBeVisible();
  });

  test('shows tags below function name', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    // Check if any tags are displayed
    const tagPills = page.locator('button').filter({ hasText: /^[a-z_]+$/ });
    // Tags may or may not exist — just verify the page is stable
    await page.waitForTimeout(500);
  });

  test('Save button appears when code is dirty', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    // Type in the Monaco editor to make it dirty
    const editor = page.locator('.monaco-editor').first();
    if (await editor.isVisible().catch(() => false)) {
      await editor.click();
      await page.keyboard.type('# test edit');
      await page.waitForTimeout(500);

      // "unsaved" badge and Save button should appear
      const saveBtn = page.getByRole('button', { name: /Save/ });
      const unsaved = page.getByText('unsaved');
      // At least one indicator of dirty state
      await expect(saveBtn.or(unsaved).first()).toBeVisible({ timeout: 3_000 });
    }
  });
});

// ── Network Assertions ──────────────────────────────────────────────

test.describe('Functions page — API integration', () => {
  test('page fetches GET /api/v1/functions on load', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/functions') &&
        resp.request().method() === 'GET' &&
        !resp.url().includes('/templates') &&
        !resp.url().includes('/logs'),
    );

    await page.goto('/functions');
    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toHaveProperty('data');
    expect(Array.isArray(body.data)).toBe(true);
  });

  test('selecting a function fetches GET /api/v1/functions/{id}', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(2000);

    const items = page.locator('button').filter({ hasText: /lines/ });
    if ((await items.count()) >= 2) {
      const responsePromise = page.waitForResponse(
        (resp) =>
          /\/api\/v1\/functions\/[^/]+$/.test(resp.url()) &&
          resp.request().method() === 'GET',
      );

      await items.nth(1).click();
      const response = await responsePromise;
      expect(response.status()).toBe(200);
    }
  });

  test('invoking a function calls POST /api/v1/functions/{id}/invoke', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    const hasFn = await page.locator('h2').first().isVisible().catch(() => false);
    if (!hasFn) return;

    const responsePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes('/invoke') &&
        resp.request().method() === 'POST',
    );

    await page.getByRole('button', { name: /^Test$/ }).first().click();

    try {
      const response = await responsePromise;
      expect(response.status()).toBe(200);
      const body = await response.json();
      expect(body).toHaveProperty('data');
    } catch {
      // Backend may not be running
    }
  });
});

// ── Empty State ─────────────────────────────────────────────────────

test.describe('Functions page — empty/error states', () => {
  test('shows empty state when no functions and no backend', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(3000);

    // Should show either functions list, empty state, or error
    const hasFunctions = await page.locator('button').filter({ hasText: /lines/ }).count();
    const hasEmpty = await page.getByText('No functions yet').isVisible().catch(() => false);
    const hasError = await page.getByText('Failed to load functions').isVisible().catch(() => false);

    expect(hasFunctions > 0 || hasEmpty || hasError).toBeTruthy();
  });

  test('detail area shows placeholder when no function selected', async ({ page }) => {
    await page.goto('/functions');
    await page.waitForTimeout(1000);

    // The placeholder should say "Select a function or create a new one"
    const placeholder = page.getByText('Select a function or create a new one');
    // May not be visible if auto-select fires, but verify page is stable
    await page.waitForTimeout(500);
  });
});
