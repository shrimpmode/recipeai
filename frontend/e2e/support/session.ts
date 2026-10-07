import { expect, type Page } from "@playwright/test";

import type { TestUser } from "./stack";

export async function logIn(page: Page, user: TestUser): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Username").fill(user.username);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "What would you like to eat?" })).toBeVisible();
}
