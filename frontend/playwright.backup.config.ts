import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './tests/backup',
  outputDir: 'test-results-backup',
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  use: { trace: 'retain-on-failure' },
  projects: [
    {
      name: 'desktop',
      use: { baseURL: 'http://127.0.0.1:8018', viewport: { width: 1440, height: 1000 } },
    },
    {
      name: 'mobile',
      use: {
        ...devices['iPhone 13'],
        defaultBrowserType: 'chromium',
        baseURL: 'http://127.0.0.1:8019',
      },
    },
  ],
  webServer: [8018, 8019].map((port) => ({
    command: 'cd .. && uv run --frozen python scripts/run_web_smoke.py --port ' + port,
    url: 'http://127.0.0.1:' + port + '/health/ready',
    reuseExistingServer: false,
  })),
})
