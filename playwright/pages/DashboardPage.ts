import { type Page } from '@playwright/test';

export class DashboardPage {
  constructor(private readonly page: Page) {}

  student() {
    return this.page.getByTestId('student-dashboard');
  }

  lecturer() {
    return this.page.getByTestId('lecturer-dashboard');
  }

  admin() {
    return this.page.getByTestId('admin-dashboard');
  }

  catalogueLink() {
    return this.page.getByTestId('dashboard-catalogue-link');
  }

  timetableLink() {
    return this.page.getByTestId('dashboard-timetable-link');
  }

  enrollmentsLink() {
    return this.page.getByTestId('dashboard-enrollments-link');
  }

  mySectionsLink() {
    return this.page.getByTestId('dashboard-my-sections-link');
  }

  termWindowsLink() {
    return this.page.getByTestId('dashboard-term-windows-link');
  }

  overrideLink() {
    return this.page.getByTestId('dashboard-override-link');
  }
}
