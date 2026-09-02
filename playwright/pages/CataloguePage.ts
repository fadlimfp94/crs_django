import { type Page } from '@playwright/test';

export class CataloguePage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto('/catalogue/');
  }

  async search(query: string) {
    await this.page.locator('#id_q').fill(query);
    await this.submitFilters();
  }

  async selectDepartment(label: string) {
    await this.page.locator('#id_department').selectOption({ label });
  }

  async selectTerm(label: string) {
    await this.page.locator('#id_term').selectOption({ label });
  }

  async submitFilters() {
    await this.page.getByTestId('catalogue-filter-submit').click();
  }

  rows() {
    return this.page.getByTestId('catalogue-row');
  }

  async openFirstResult() {
    await this.openResult(0);
  }

  /** Opens the section detail page for the nth (0-indexed) matching row. */
  async openResult(index: number) {
    await this.rows().nth(index).getByTestId('catalogue-row-view').click();
  }

  /** Search for one course code, optionally in a specific term, and open its first (lowest section-code) result. */
  async openCourse(courseCode: string, termLabel?: string) {
    await this.goto();
    if (termLabel) await this.selectTerm(termLabel);
    await this.page.locator('#id_q').fill(courseCode);
    await this.submitFilters();
    await this.openFirstResult();
  }

  nextPage() {
    return this.page.getByTestId('catalogue-page-next');
  }

  prevPage() {
    return this.page.getByTestId('catalogue-page-prev');
  }

  currentPage() {
    return this.page.getByTestId('catalogue-page-current');
  }

  empty() {
    return this.page.getByTestId('catalogue-empty');
  }
}
