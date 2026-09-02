import { test as base, type Page } from '@playwright/test';
import path from 'path';

const AUTH_DIR = path.resolve(__dirname, '..', '.auth');

interface AuthFixtures {
  studentPage: Page;
  lecturerPage: Page;
  adminPage: Page;
}

// Specs import `test`/`expect` from here instead of '@playwright/test'
// directly whenever they only need to browse as one of the three
// pre-authenticated roles — cheaper than logging in through the UI in every
// test, and the storage states are produced once by tests/setup/auth.setup.ts.
export const test = base.extend<AuthFixtures>({
  studentPage: async ({ browser }, use) => {
    const context = await browser.newContext({ storageState: path.join(AUTH_DIR, 'student.json') });
    await use(await context.newPage());
    await context.close();
  },
  lecturerPage: async ({ browser }, use) => {
    const context = await browser.newContext({ storageState: path.join(AUTH_DIR, 'lecturer.json') });
    await use(await context.newPage());
    await context.close();
  },
  adminPage: async ({ browser }, use) => {
    const context = await browser.newContext({ storageState: path.join(AUTH_DIR, 'admin.json') });
    await use(await context.newPage());
    await context.close();
  },
});

export { expect } from '@playwright/test';
