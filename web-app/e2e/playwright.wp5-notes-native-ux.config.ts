import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './probes',
  testMatch: 'wp5-notes-native-ux.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  outputDir: process.env.SB_E2E_RAW_ARTIFACTS
    ? `${process.env.SB_E2E_RAW_ARTIFACTS}/test-results`
    : './artifacts-raw/wp5-notes-native-ux',
  reporter: [['list']],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.SB_E2E_BASE_URL ?? 'http://127.0.0.1:4173',
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
});
