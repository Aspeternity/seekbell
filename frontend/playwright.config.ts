import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './tests',
  testIgnore: ['**/live/**', '**/history/**', '**/sending/**'],
  fullyParallel: true,
  workers: 4,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5174', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: {
    command: 'pnpm dev:prototype',
    url: 'http://127.0.0.1:5174/prototype.html',
    reuseExistingServer: !process.env.CI,
  },
})
