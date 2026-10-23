import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './tests/workspace-stability',
  outputDir: 'test-results-workspace-stability',
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:8025', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: {
    command: 'cd .. && uv run --frozen python scripts/run_web_smoke.py --history --port 8025',
    url: 'http://127.0.0.1:8025/health/ready',
    reuseExistingServer: false,
  },
})
