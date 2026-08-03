import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/screens',
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
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },
  ],
});
