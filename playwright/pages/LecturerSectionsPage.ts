import { type Page } from '@playwright/test';

export class LecturerSectionsPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto('/registration/my-sections/');
  }

  rows() {
    return this.page.getByTestId('lecturer-sections-row');
  }

  async openRoster(courseCode: string) {
    await this.rows().filter({ hasText: courseCode }).first().getByTestId('lecturer-sections-roster').click();
  }
}
