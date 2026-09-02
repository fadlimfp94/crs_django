import { type Page } from '@playwright/test';

export class SectionDetailPage {
  constructor(private readonly page: Page) {}

  seats() {
    return this.page.getByTestId('section-seats');
  }

  actionStatus() {
    return this.page.getByTestId('section-action-status');
  }

  lecturer() {
    return this.page.getByTestId('section-lecturer');
  }

  meetings() {
    return this.page.getByTestId('section-meetings');
  }

  registerLink() {
    return this.page.getByTestId('section-register-link');
  }

  dropLink() {
    return this.page.getByTestId('section-drop-link');
  }

  async register() {
    await this.registerLink().click();
  }

  async drop() {
    await this.dropLink().click();
  }
}
