import { type Page } from '@playwright/test';

export class MyTimetablePage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto('/registration/my-timetable/');
  }

  blocks() {
    return this.page.getByTestId('timetable-block');
  }

  empty() {
    return this.page.getByTestId('timetable-empty');
  }
}
