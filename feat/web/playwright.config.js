import { defineConfig, devices } from '@playwright/test';

const port = Number(process.env.ACM_E2E_PORT || 18761);
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw Error('Invalid ACM_E2E_PORT');
const python = process.env.ACM_E2E_PYTHON || 'python';
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 45000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: process.env.ACM_E2E_BROWSER
      ? { executablePath: process.env.ACM_E2E_BROWSER }
      : {},
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 5'] } },
  ],
  webServer: {
    command: `"${python}" e2e/server.py --port ${port}`,
    url: `http://127.0.0.1:${port}/health`,
    reuseExistingServer: false,
    timeout: 30000,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 5000 },
  },
});
