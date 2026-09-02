import { defineConfig, devices } from '@playwright/test';
import baseConfig from './playwright.config';

// Chromium is the gate (bare `npx playwright test`); Firefox and WebKit run
// here, nightly, so a cross-browser regression doesn't block every commit.
export default defineConfig(baseConfig, {
  projects: [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    { name: 'chromium', use: { ...devices['Desktop Chrome'] }, dependencies: ['setup'] },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] }, dependencies: ['setup'] },
    { name: 'webkit', use: { ...devices['Desktop Safari'] }, dependencies: ['setup'] },
  ],
});
