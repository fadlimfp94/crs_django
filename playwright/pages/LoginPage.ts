import { type Page } from '@playwright/test';

export class LoginPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto('/accounts/login/');
  }

  async signIn(username: string, password: string) {
    await this.page.getByTestId('login-username').fill(username);
    await this.page.getByTestId('login-password').fill(password);
    await this.page.getByTestId('login-submit').click();
  }

  error() {
    return this.page.getByTestId('login-error');
  }
}
