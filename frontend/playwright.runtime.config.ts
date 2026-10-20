import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './tests/runtime',
  outputDir: 'test-results-runtime',
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  timeout: 45000,
  use: { baseURL: 'http://127.0.0.1:8014', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: {
    command: 'cd .. && uv run --frozen python scripts/run_web_smoke.py --runtime',
    url: 'http://127.0.0.1:8014/health/ready',
    reuseExistingServer: false,
  },
})
