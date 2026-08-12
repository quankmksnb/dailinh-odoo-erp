import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  reporter: [['html', { outputFolder: 'tests/reports/html' }], ['list']],
  use: {
    baseURL: process.env.DLM_BASE_URL || 'http://127.0.0.1:8069',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    headless: false,
  },
  projects: [
    {
      name: 'setup',
      testMatch: /.*\.setup\.ts/,
    },
    {
      name: 'chromium',
      testDir: './tests/screens',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },
    {
      // §3a HTTP Flow Testing — JSON-RPC thuần, không cần browser/storageState.
      name: 'http',
      testDir: './tests/http',
      use: { baseURL: process.env.DLM_BASE_URL || 'http://127.0.0.1:8069' },
    },
  ],
});
