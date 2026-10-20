import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './tests/history',
  outputDir: 'test-results-history',
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:8012', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: {
    command: 'cd .. && uv run --frozen python scripts/run_web_smoke.py --history',
    url: 'http://127.0.0.1:8012/health/ready',
    reuseExistingServer: false,
  },
})
