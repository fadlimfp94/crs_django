import { type Page } from '@playwright/test';

export class DropConfirmPage {
  constructor(private readonly page: Page) {}

  async confirm() {
    await this.page.getByTestId('drop-confirm-submit').click();
  }
}
