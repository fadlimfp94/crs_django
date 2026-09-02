import { defineConfig, devices } from '@playwright/test';

const port = process.env.CRS_E2E_PORT ?? '8765';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  // Deliberately 0: the done-when bar is "stable over 3 consecutive runs with
  // no flakes," and retries would mask a flake instead of revealing it.
  retries: 0,
  reporter: 'html',
  globalSetup: require.resolve('./utils/global-setup'),
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },
  ],
});
