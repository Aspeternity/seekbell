import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:18765',
    browserName: 'chromium',
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'cd .. && uv run --frozen python -m tests.browser_server',
    url: 'http://127.0.0.1:18765/health/ready',
    reuseExistingServer: false,
  },
})
