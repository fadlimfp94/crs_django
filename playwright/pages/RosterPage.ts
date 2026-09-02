import { type Page } from '@playwright/test';

export class RosterPage {
  constructor(private readonly page: Page) {}

  enrolledRow(studentNumber: string) {
    return this.page.getByTestId('roster-enrolled-row').filter({ hasText: studentNumber });
  }

  waitlistRow(studentNumber: string) {
    return this.page.getByTestId('roster-waitlist-row').filter({ hasText: studentNumber });
  }

  async recordGrade(studentNumber: string, grade: string) {
    const row = this.enrolledRow(studentNumber);
    await row.locator('select[name="grade"]').selectOption(grade);
    await row.getByTestId('roster-grade-submit').click();
  }

  successMessage() {
    return this.page.getByTestId('message-success');
  }
}
