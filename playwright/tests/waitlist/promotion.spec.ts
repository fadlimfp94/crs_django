import { test, expect } from '@playwright/test';
import { LoginPage } from '../../pages/LoginPage';
import { CataloguePage } from '../../pages/CataloguePage';
import { SectionDetailPage } from '../../pages/SectionDetailPage';
import { RegisterConfirmPage } from '../../pages/RegisterConfirmPage';
import { DropConfirmPage } from '../../pages/DropConfirmPage';
import { PASSWORD, STUDENTS } from '../../fixtures/users';
import { RULE_COURSES, TERM_NAMES } from '../../fixtures/sections';

test('a full section waitlists the next registrant, then promotes them on a drop', async ({ browser }) => {
  const firstContext = await browser.newContext();
  const firstPage = await firstContext.newPage();
  const secondContext = await browser.newContext();
  const secondPage = await secondContext.newPage();

  const firstLogin = new LoginPage(firstPage);
  const firstCatalogue = new CataloguePage(firstPage);
  const firstDetail = new SectionDetailPage(firstPage);
  const firstRegisterConfirm = new RegisterConfirmPage(firstPage);
  const firstDropConfirm = new DropConfirmPage(firstPage);

  const secondLogin = new LoginPage(secondPage);
  const secondCatalogue = new CataloguePage(secondPage);
  const secondDetail = new SectionDetailPage(secondPage);
  const secondRegisterConfirm = new RegisterConfirmPage(secondPage);

  await secondLogin.goto();
  await secondLogin.signIn(STUDENTS.waitlistSecond.username, PASSWORD);
  await firstLogin.goto();
  await firstLogin.signIn(STUDENTS.waitlistFirst.username, PASSWORD);

  await firstCatalogue.openCourse(RULE_COURSES.waitlist, TERM_NAMES.fall);
  await firstDetail.register();
  await firstRegisterConfirm.confirm();
  await expect(firstDetail.actionStatus()).toContainText('Enrolled');

  await secondCatalogue.openCourse(RULE_COURSES.waitlist, TERM_NAMES.fall);
  await secondDetail.register();
  await secondRegisterConfirm.confirm();
  await expect(secondDetail.actionStatus()).toContainText('position 1');

  await firstDetail.drop();
  await firstDropConfirm.confirm();

  await secondPage.reload();
  await expect(secondDetail.actionStatus()).toContainText('Enrolled');

  await firstContext.close();
  await secondContext.close();
});
