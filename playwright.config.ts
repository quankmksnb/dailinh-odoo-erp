import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  reporter: [['html', { outputFolder: 'tests/reports/html' }], ['list']],
  use: {
    baseURL: process.env.DLM_BASE_URL || 'http://127.0.0.1:8069',
    trace: 'on',
    screenshot: 'on',
    video: 'retain-on-failure',
    headless: false,
  },
  projects: [
    {
      name: 'setup',
      testDir: './tests/screens',
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
    {
      // Bản đã deploy (https://erp.dailinh.com, db dlm_prod) — tách hẳn khỏi 'setup'/'chromium'
      // (dlm_dev cục bộ) để không lẫn storageState/tài khoản 2 môi trường vào nhau.
      name: 'setup-staging',
      testDir: './tests/screens-staging',
      testMatch: /.*\.setup\.ts/,
      use: { baseURL: process.env.STAGING_BASE_URL || 'https://erp.dailinh.com' },
    },
    {
      name: 'staging',
      testDir: './tests/screens-staging',
      testIgnore: /.*\.setup\.ts/,
      use: { ...devices['Desktop Chrome'], baseURL: process.env.STAGING_BASE_URL || 'https://erp.dailinh.com' },
      dependencies: ['setup-staging'],
    },
    {
      name: 'http-staging',
      testDir: './tests/http-staging',
      use: { baseURL: process.env.STAGING_BASE_URL || 'https://erp.dailinh.com' },
    },
  ],
});
