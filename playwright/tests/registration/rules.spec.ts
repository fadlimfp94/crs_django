import { test, expect } from '@playwright/test';
import { LoginPage } from '../../pages/LoginPage';
import { CataloguePage } from '../../pages/CataloguePage';
import { SectionDetailPage } from '../../pages/SectionDetailPage';
import { RegisterConfirmPage } from '../../pages/RegisterConfirmPage';
import { PASSWORD, STUDENTS } from '../../fixtures/users';
import { RULE_COURSES, TERM_NAMES } from '../../fixtures/sections';

async function signIn(page: import('@playwright/test').Page, username: string) {
  const login = new LoginPage(page);
  await login.goto();
  await login.signIn(username, PASSWORD);
}

test('happy path: registering for an open section shows Enrolled', async ({ page }) => {
  await signIn(page, STUDENTS.happyPath.username);
  const catalogue = new CataloguePage(page);
  const detail = new SectionDetailPage(page);
  const confirm = new RegisterConfirmPage(page);
  await catalogue.openCourse(RULE_COURSES.happyPath, TERM_NAMES.fall);
  await detail.register();
  await confirm.confirm();
  await expect(detail.actionStatus()).toContainText('Enrolled');
});

test('R1: registering into a closed term is rejected', async ({ page }) => {
  await signIn(page, STUDENTS.closedWindow.username);
  const catalogue = new CataloguePage(page);
  const detail = new SectionDetailPage(page);
  const confirm = new RegisterConfirmPage(page);
  await catalogue.openCourse(RULE_COURSES.closedWindow, TERM_NAMES.spring);
  await detail.register();
  await confirm.confirm();
  await expect(confirm.error()).toContainText('is not currently open');
});

test('R2: registering into a second section of an already-registered course is rejected', async ({ page }) => {
  await signIn(page, STUDENTS.duplicate.username);
  const catalogue = new CataloguePage(page);
  const detail = new SectionDetailPage(page);
  const confirm = new RegisterConfirmPage(page);

  await catalogue.openCourse(RULE_COURSES.duplicate, TERM_NAMES.fall);
  await detail.register();
  await confirm.confirm();
  await expect(detail.actionStatus()).toContainText('Enrolled');

  await catalogue.goto();
  await catalogue.selectTerm(TERM_NAMES.fall);
  await catalogue.search(RULE_COURSES.duplicate);
  await catalogue.openResult(1);
  await detail.register();
  await confirm.confirm();
  await expect(confirm.error()).toContainText('already registered or waitlisted');
});

test('R3: registering without the required prerequisite is rejected', async ({ page }) => {
  await signIn(page, STUDENTS.default.username);
  const catalogue = new CataloguePage(page);
  const detail = new SectionDetailPage(page);
  const confirm = new RegisterConfirmPage(page);
  await catalogue.openCourse(RULE_COURSES.prerequisite, TERM_NAMES.fall);
  await detail.register();
  await confirm.confirm();
  await expect(confirm.error()).toContainText('requires');
});

test('R4: registering over the term credit ceiling is rejected', async ({ page }) => {
  await signIn(page, STUDENTS.overload.username);
  const catalogue = new CataloguePage(page);
  const detail = new SectionDetailPage(page);
  const confirm = new RegisterConfirmPage(page);
  await catalogue.openCourse(RULE_COURSES.overloadAttempt, TERM_NAMES.fall);
  await detail.register();
  await confirm.confirm();
  await expect(confirm.error()).toContainText('would exceed the');
});

test('R5: registering into a clashing section is rejected', async ({ page }) => {
  await signIn(page, STUDENTS.clash.username);
  const catalogue = new CataloguePage(page);
  const detail = new SectionDetailPage(page);
  const confirm = new RegisterConfirmPage(page);
  await catalogue.openCourse(RULE_COURSES.clashAttempt, TERM_NAMES.fall);
  await detail.register();
  await confirm.confirm();
  await expect(confirm.error()).toContainText('clashes with');
});

test('R7: a student not in good standing cannot register', async ({ page }) => {
  await signIn(page, STUDENTS.probation.username);
  const catalogue = new CataloguePage(page);
  const detail = new SectionDetailPage(page);
  const confirm = new RegisterConfirmPage(page);
  await catalogue.openCourse(RULE_COURSES.standing, TERM_NAMES.fall);
  await detail.register();
  await confirm.confirm();
  await expect(confirm.error()).toContainText('academic standing does not permit registration');
});
