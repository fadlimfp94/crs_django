import { type Page } from '@playwright/test';

export class AdminOverridePage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto('/registration/admin/override/');
  }

  async selectStudent(label: string) {
    await this.page.locator('#id_student').selectOption({ label });
  }

  async selectSection(label: string) {
    await this.page.locator('#id_section').selectOption({ label });
  }

  async apply() {
    await this.page.getByTestId('admin-override-submit').click();
  }

  successMessage() {
    return this.page.getByTestId('message-success');
  }

  errorMessage() {
    return this.page.getByTestId('message-error');
  }
}
