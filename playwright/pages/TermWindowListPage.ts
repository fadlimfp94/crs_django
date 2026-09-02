import { type Page } from '@playwright/test';

export class TermWindowListPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto('/catalogue/admin/terms/');
  }

  rows() {
    return this.page.getByTestId('term-window-row');
  }

  async edit(termLabel: string) {
    await this.rows().filter({ hasText: termLabel }).first().getByTestId('term-window-edit').click();
  }
}
