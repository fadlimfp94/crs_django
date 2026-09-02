import { test, expect } from '@playwright/test';
import { LoginPage } from '../../pages/LoginPage';
import { CataloguePage } from '../../pages/CataloguePage';
import { SectionDetailPage } from '../../pages/SectionDetailPage';
import { RegisterConfirmPage } from '../../pages/RegisterConfirmPage';
import { DropConfirmPage } from '../../pages/DropConfirmPage';
import { PASSWORD, STUDENTS } from '../../fixtures/users';
import { TERM_NAMES } from '../../fixtures/sections';

test('registering then dropping returns the section to Register', async ({ page }) => {
  const login = new LoginPage(page);
  const catalogue = new CataloguePage(page);
  const detail = new SectionDetailPage(page);
  const registerConfirm = new RegisterConfirmPage(page);
  const dropConfirm = new DropConfirmPage(page);

  await login.goto();
  await login.signIn(STUDENTS.default.username, PASSWORD);

  await catalogue.openCourse('CS102', TERM_NAMES.fall);
  await detail.register();
  await registerConfirm.confirm();
  await expect(detail.actionStatus()).toContainText('Enrolled');

  await detail.drop();
  await dropConfirm.confirm();

  await catalogue.openCourse('CS102', TERM_NAMES.fall);
  await expect(detail.registerLink()).toBeVisible();
});
