import { test as setup } from '@playwright/test';
import path from 'path';
import { LoginPage } from '../../pages/LoginPage';
import { DashboardPage } from '../../pages/DashboardPage';
import { ADMIN, LECTURER, PASSWORD, STUDENTS } from '../../fixtures/users';

const AUTH_DIR = path.resolve(__dirname, '..', '..', '.auth');

setup('authenticate as student', async ({ page }) => {
  const login = new LoginPage(page);
  const dashboard = new DashboardPage(page);
  await login.goto();
  await login.signIn(STUDENTS.default.username, PASSWORD);
  await dashboard.student().waitFor();
  await page.context().storageState({ path: path.join(AUTH_DIR, 'student.json') });
});

setup('authenticate as lecturer', async ({ page }) => {
  const login = new LoginPage(page);
  const dashboard = new DashboardPage(page);
  await login.goto();
  await login.signIn(LECTURER.username, PASSWORD);
  await dashboard.lecturer().waitFor();
  await page.context().storageState({ path: path.join(AUTH_DIR, 'lecturer.json') });
});

setup('authenticate as admin', async ({ page }) => {
  const login = new LoginPage(page);
  const dashboard = new DashboardPage(page);
  await login.goto();
  await login.signIn(ADMIN.username, PASSWORD);
  await dashboard.admin().waitFor();
  await page.context().storageState({ path: path.join(AUTH_DIR, 'admin.json') });
});
