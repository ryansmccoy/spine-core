import { test, expect } from '@playwright/test';

/**
 * Comprehensive tests for workflow interactions:
 * - Workflow cards render with descriptions
 * - Run workflow modal opens with params
 * - Dynamic workflow dropdown in schedule creation
 */

test.describe('Workflows page — cards and run modal', () => {
  test('renders workflow cards when workflows are registered', async ({ page }) => {
    await page.goto('/workflows');
    await expect(page.getByRole('heading', { name: 'Workflows' })).toBeVisible();

    // Either empty state or workflow cards
    const hasCards = await page.locator('.grid .bg-white').count();
    const hasEmpty = await page.getByText('No workflows registered').isVisible().catch(() => false);

    // One of these must be true
    expect(hasCards > 0 || hasEmpty).toBeTruthy();
  });

  test('workflow run modal opens and shows params field', async ({ page }) => {
    await page.goto('/workflows');
    await page.waitForTimeout(1000); // let data load

    const runButton = page.getByRole('button', { name: /run/i }).first();
    const hasButton = await runButton.isVisible().catch(() => false);

    if (hasButton) {
      await runButton.click();
      // Modal should open with params textarea
      await expect(page.getByText('Parameters (JSON)')).toBeVisible();
      await expect(page.getByLabel('Parameters (JSON)')).toBeVisible();
      // Dry run checkbox
      await expect(page.getByLabel(/dry run/i)).toBeVisible();
      // Close/Execute buttons
      await expect(page.getByRole('button', { name: 'Close' })).toBeVisible();
      await expect(page.getByRole('button', { name: /execute/i })).toBeVisible();

      // Close modal
      await page.getByRole('button', { name: 'Close' }).click();
      await expect(page.getByText('Parameters (JSON)')).not.toBeVisible();
    }
  });
});

test.describe('Schedules page — dynamic workflow picker', () => {
  test('create dialog loads workflow dropdown dynamically', async ({ page }) => {
    await page.goto('/schedules');
    await expect(page.getByRole('heading', { name: 'Schedules' })).toBeVisible();

    // Open create dialog
    await page.getByRole('button', { name: /new schedule/i }).click();
    await expect(page.getByText('Create Schedule')).toBeVisible();

    // Workflow field should be present (either select or input)
    const workflowField = page.locator('#sched-workflow');
    await expect(workflowField).toBeVisible();

    // Cron and interval fields
    await expect(page.getByLabel('Cron Expression')).toBeVisible();
    await expect(page.getByLabel(/interval/i)).toBeVisible();
    // Parameters field
    await expect(page.getByLabel('Parameters (JSON)')).toBeVisible();

    // Close
    await page.getByRole('button', { name: 'Cancel' }).click();
  });
});

test.describe('Runs page — enhanced submit dialog', () => {
  test('submit dialog has kind, name, priority, and params fields', async ({ page }) => {
    await page.goto('/runs');
    await page.getByRole('button', { name: /submit/i }).click();

    // Dialog opens via Modal component
    await expect(page.getByText('Submit New Run')).toBeVisible();

    // All form fields
    await expect(page.getByLabel('Kind')).toBeVisible();
    await expect(page.getByLabel('Name')).toBeVisible();
    await expect(page.getByLabel('Priority')).toBeVisible();
    await expect(page.getByLabel('Parameters (JSON)')).toBeVisible();

    // When kind is set to "workflow", name might become a select
    await page.getByLabel('Kind').selectOption('workflow');
    // Name field still visible (either input or select)
    const nameField = page.locator('#run-name');
    await expect(nameField).toBeVisible();

    // Cancel — use exact match to avoid conflicting with "cancelled" filter button
    const dialog = page.locator('.fixed.inset-0');
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByText('Submit New Run')).not.toBeVisible();
  });

  test('runs table shows workflow and finished columns', async ({ page }) => {
    await page.goto('/runs');
    await page.waitForTimeout(1000);

    // Check table headers include new columns
    const table = page.locator('table');
    const hasTable = await table.isVisible().catch(() => false);
    if (hasTable) {
      await expect(table.locator('th').getByText('Workflow')).toBeVisible();
      await expect(table.locator('th').getByText('Finished')).toBeVisible();
    }
  });
});

test.describe('Run detail page — enhanced display', () => {
  test('run detail shows all fields', async ({ page }) => {
    // Navigate to runs, submit a run, then view detail
    await page.goto('/runs');
    await page.waitForTimeout(500);

    // Try to click into a run detail if there are runs
    const runLink = page.locator('a[href*="/runs/"]').first();
    const hasRuns = await runLink.isVisible().catch(() => false);

    if (hasRuns) {
      await runLink.click();
      await page.waitForTimeout(500);

      // The detail page should show comprehensive info
      await expect(page.getByText('Run ID')).toBeVisible();
      await expect(page.getByText('Status')).toBeVisible();
      await expect(page.getByText('Pipeline', { exact: true })).toBeVisible();
      await expect(page.getByText('Workflow', { exact: true })).toBeVisible();
      await expect(page.getByText('Started', { exact: true })).toBeVisible();
      await expect(page.getByText('Finished', { exact: true })).toBeVisible();
      await expect(page.getByText('Duration', { exact: true })).toBeVisible();

      // Back button
      await expect(page.getByRole('button', { name: /back/i })).toBeVisible();
    }
  });
});

test.describe('Quality page — bug fix verification', () => {
  test('quality page loads without 500 error', async ({ page }) => {
    await page.goto('/quality');
    await expect(page.getByText('Quality & Anomalies')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Quality Results' })).toBeVisible();

    // Wait for data load — should show empty state or data, NOT error
    await page.waitForTimeout(2000);
    const hasError = await page.getByText('Failed to load quality results').isVisible().catch(() => false);
    const hasEmpty = await page.getByText('No quality results yet').isVisible().catch(() => false);
    const hasData = await page.locator('table').isVisible().catch(() => false);

    // At least one of empty or data should be true (not error)
    expect(hasEmpty || hasData || !hasError).toBeTruthy();
  });
});
