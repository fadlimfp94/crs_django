import { test, expect } from '@playwright/test';
import { LoginPage } from '../../pages/LoginPage';
import { DashboardPage } from '../../pages/DashboardPage';
import { ADMIN, LECTURER, PASSWORD, STUDENTS } from '../../fixtures/users';

test('student logs in and lands on the student dashboard', async ({ page }) => {
  const login = new LoginPage(page);
  const dashboard = new DashboardPage(page);
  await login.goto();
  await login.signIn(STUDENTS.default.username, PASSWORD);
  await expect(dashboard.student()).toBeVisible();
});

test('lecturer logs in and lands on the lecturer dashboard', async ({ page }) => {
  const login = new LoginPage(page);
  const dashboard = new DashboardPage(page);
  await login.goto();
  await login.signIn(LECTURER.username, PASSWORD);
  await expect(dashboard.lecturer()).toBeVisible();
});

test('administrator logs in and lands on the admin dashboard', async ({ page }) => {
  const login = new LoginPage(page);
  const dashboard = new DashboardPage(page);
  await login.goto();
  await login.signIn(ADMIN.username, PASSWORD);
  await expect(dashboard.admin()).toBeVisible();
});

test('bad credentials show an error and no redirect', async ({ page }) => {
  const login = new LoginPage(page);
  await login.goto();
  await login.signIn(STUDENTS.default.username, 'wrong-password');
  await expect(login.error()).toBeVisible();
  await expect(page).toHaveURL(/\/accounts\/login\//);
});

test('logout returns to the login page', async ({ page }) => {
  const login = new LoginPage(page);
  const dashboard = new DashboardPage(page);
  await login.goto();
  await login.signIn(STUDENTS.default.username, PASSWORD);
  await expect(dashboard.student()).toBeVisible();
  await page.getByTestId('logout-button').click();
  await expect(page).toHaveURL(/\/accounts\/login\//);
});

test('an unauthenticated request to a protected page redirects to login', async ({ page }) => {
  await page.goto('/registration/my-timetable/');
  await expect(page).toHaveURL(/\/accounts\/login\//);
});
