import { expect, test } from "@playwright/test";

import { createUser } from "./support/stack";

test("signed-out visitors are sent to log in, then back where they were going", async ({ page }) => {
  const user = createUser();

  await page.goto("/goals");
  await expect(page).toHaveURL(/\/login\?next=%2Fgoals$/);

  await page.getByLabel("Username").fill(user.username);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(page.getByRole("heading", { name: "Nutrition goals" })).toBeVisible();
});

test("a wrong password is refused", async ({ page }) => {
  const user = createUser();

  await page.goto("/login");
  await page.getByLabel("Username").fill(user.username);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Log in" }).click();

  // Filtered by text: Next.js renders its own (empty) role="alert" route announcer.
  await expect(page.getByRole("alert").filter({ hasText: "That username and password don’t match." })).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("logging out ends the session", async ({ page }) => {
  const user = createUser();
  await page.goto("/login");
  await page.getByLabel("Username").fill(user.username);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Log in" }).click();

  await page.getByRole("button", { name: "Log out" }).click();

  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
});
