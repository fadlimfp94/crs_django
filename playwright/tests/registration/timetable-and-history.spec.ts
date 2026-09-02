import { test, expect } from '../../fixtures/auth';
import { MyTimetablePage } from '../../pages/MyTimetablePage';
import { EnrollmentHistoryPage } from '../../pages/EnrollmentHistoryPage';

test('my timetable page loads for a student', async ({ studentPage }) => {
  const timetable = new MyTimetablePage(studentPage);
  await timetable.goto();
  await expect(studentPage.getByTestId('my-timetable')).toBeVisible();
});

test('my enrollments page loads for a student', async ({ studentPage }) => {
  const history = new EnrollmentHistoryPage(studentPage);
  await history.goto();
  await expect(studentPage.getByTestId('enrollment-history')).toBeVisible();
});
