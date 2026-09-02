import { test, expect } from '../../fixtures/auth';
import { LecturerSectionsPage } from '../../pages/LecturerSectionsPage';
import { RosterPage } from '../../pages/RosterPage';
import { RULE_COURSES } from '../../fixtures/sections';
import { STUDENTS } from '../../fixtures/users';

test('a lecturer records a grade for an enrolled student', async ({ lecturerPage }) => {
  const sections = new LecturerSectionsPage(lecturerPage);
  const roster = new RosterPage(lecturerPage);

  await sections.goto();
  await sections.openRoster(RULE_COURSES.grademe);

  await expect(roster.enrolledRow(STUDENTS.grademe.username)).toBeVisible();
  await roster.recordGrade(STUDENTS.grademe.username, 'A');

  await expect(roster.successMessage()).toBeVisible();
  // Grading moves the enrollment to COMPLETED, which drops it off the roster's
  // "Enrolled" table entirely (roster.html has no completed-students table).
  await expect(roster.enrolledRow(STUDENTS.grademe.username)).toHaveCount(0);
});
