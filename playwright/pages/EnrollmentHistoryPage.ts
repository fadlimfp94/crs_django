import { type Page } from '@playwright/test';

export class EnrollmentHistoryPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto('/registration/my-enrollments/');
  }

  rows() {
    return this.page.getByTestId('enrollment-history-row');
  }

  empty() {
    return this.page.getByTestId('enrollment-history-empty');
  }
}
