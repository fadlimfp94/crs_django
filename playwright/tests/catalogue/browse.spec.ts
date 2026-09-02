import { test, expect } from '../../fixtures/auth';
import { CataloguePage } from '../../pages/CataloguePage';
import { SectionDetailPage } from '../../pages/SectionDetailPage';
import { TERM_NAMES } from '../../fixtures/sections';

test('filtering by department narrows the catalogue to that department', async ({ studentPage }) => {
  const catalogue = new CataloguePage(studentPage);
  await catalogue.goto();
  await catalogue.selectDepartment('E2E — E2E Fixtures');
  await catalogue.submitFilters();
  const rows = catalogue.rows();
  await expect(rows.first()).toBeVisible();
  const count = await rows.count();
  for (let i = 0; i < count; i++) {
    await expect(rows.nth(i)).toContainText('E2E');
  }
});

test('free-text search finds a course by code', async ({ studentPage }) => {
  const catalogue = new CataloguePage(studentPage);
  await catalogue.goto();
  await catalogue.search('CS102');
  await expect(catalogue.rows().first()).toContainText('CS102');
});

test('an unmatched search shows the empty state', async ({ studentPage }) => {
  const catalogue = new CataloguePage(studentPage);
  await catalogue.goto();
  await catalogue.search('NOSUCHCOURSE');
  await expect(catalogue.empty()).toBeVisible();
});

test('pagination advances to page 2 and back', async ({ studentPage }) => {
  const catalogue = new CataloguePage(studentPage);
  await catalogue.goto();
  await catalogue.selectTerm(TERM_NAMES.fall);
  await catalogue.submitFilters();
  await catalogue.nextPage().click();
  await expect(catalogue.currentPage()).toContainText('Page 2');
  await catalogue.prevPage().click();
  await expect(catalogue.currentPage()).toContainText('Page 1');
});

test('opening a section shows its detail data', async ({ studentPage }) => {
  const catalogue = new CataloguePage(studentPage);
  const detail = new SectionDetailPage(studentPage);
  await catalogue.openCourse('CS102', TERM_NAMES.fall);
  await expect(detail.seats()).toBeVisible();
  await expect(detail.lecturer()).not.toBeEmpty();
  await expect(detail.meetings()).toBeVisible();
});
