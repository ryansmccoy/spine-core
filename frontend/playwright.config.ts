import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E configuration for spine-core dashboard.
 *
 * Tiers correspond to docker/compose.yml profiles:
 *   - Tier 1 (minimal): API + Frontend (SQLite)
 *   - Tier 2 (standard): + PostgreSQL + Worker + Docs
 *   - Tier 3 (full): + TimescaleDB + Redis + Celery + Prometheus + Grafana
 *
 * By default tests target the frontend at localhost:12001 which proxies
 * /api/* to localhost:12000. Override via FRONTEND_URL / API_URL env vars.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],
  use: {
    baseURL: process.env.FRONTEND_URL || 'http://localhost:12001',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  /* Start the Vite dev server before tests if no Docker stack is running */
  webServer: process.env.NO_DEV_SERVER
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:12001',
        reuseExistingServer: !process.env.CI,
        timeout: 30_000,
      },
});
