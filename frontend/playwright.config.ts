import { defineConfig, devices } from '@playwright/test';

const FRONTEND_URL = 'http://localhost:5173';
const BACKEND_URL = 'http://localhost:8000';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: FRONTEND_URL,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command:
        'bash -c "rm -f data/e2e.db && .venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --port 8000 --log-level warning"',
      cwd: '../backend',
      url: `${BACKEND_URL}/health`,
      env: {
        DATABASE_URL: 'sqlite:///./data/e2e.db',
        SECRET_KEY: 'e2e-test-secret-key',
        CORS_ORIGINS: FRONTEND_URL,
        COOKIE_SECURE: 'false',
      },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort',
      url: FRONTEND_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
