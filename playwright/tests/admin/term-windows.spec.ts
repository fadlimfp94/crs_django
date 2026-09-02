import { test, expect } from '../../fixtures/auth';
import { TermWindowListPage } from '../../pages/TermWindowListPage';
import { TermWindowFormPage } from '../../pages/TermWindowFormPage';
import { TERM_NAMES } from '../../fixtures/sections';

test('editing a term window persists the new credit ceiling', async ({ adminPage }) => {
  const list = new TermWindowListPage(adminPage);
  const form = new TermWindowFormPage(adminPage);

  await list.goto();
  await list.edit(TERM_NAMES.spring);
  await form.setMaxCredits('27');
  await form.save();

  await expect(adminPage).toHaveURL(/\/catalogue\/admin\/terms\/$/);

  await list.edit(TERM_NAMES.spring);
  await expect(adminPage.locator('#id_max_credits_per_student')).toHaveValue('27');

  await form.setMaxCredits('24');
  await form.save();
});
