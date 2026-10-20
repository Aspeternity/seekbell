import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './tests/proxy',
  outputDir: 'test-results-proxy',
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  use: {
    baseURL: 'https://127.0.0.1:8020',
    trace: 'retain-on-failure',
    // Ephemeral localhost test CA; production certificate validation is checked by Python.
    ignoreHTTPSErrors: true,
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: {
    command: 'cd .. && uv run --frozen python scripts/run_proxy_smoke.py',
    url: 'https://127.0.0.1:8020/health/ready',
    ignoreHTTPSErrors: true,
    reuseExistingServer: false,
    timeout: 120000,
  },
})
