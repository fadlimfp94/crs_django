import { test, expect } from '../../fixtures/auth';
import { AdminOverridePage } from '../../pages/AdminOverridePage';
import { OVERRIDE_TARGET } from '../../fixtures/sections';

test('an administrator can force-enroll a student who would otherwise be rejected', async ({ adminPage }) => {
  const override = new AdminOverridePage(adminPage);

  await override.goto();
  await override.selectStudent(OVERRIDE_TARGET.studentLabel);
  await override.selectSection(OVERRIDE_TARGET.sectionLabel);
  await override.apply();

  await expect(override.successMessage()).toBeVisible();
});
