import { type Page } from '@playwright/test';

export class RegisterConfirmPage {
  constructor(private readonly page: Page) {}

  error() {
    return this.page.getByTestId('registration-error');
  }

  async confirm() {
    await this.page.getByTestId('register-confirm-submit').click();
  }
}
