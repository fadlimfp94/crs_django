import { type Page } from '@playwright/test';

export class TermWindowFormPage {
  constructor(private readonly page: Page) {}

  async setMaxCredits(value: string) {
    await this.page.locator('#id_max_credits_per_student').fill(value);
  }

  async save() {
    await this.page.getByTestId('term-window-save').click();
  }

  successMessage() {
    return this.page.getByTestId('message-success');
  }
}
