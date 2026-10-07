import { expect, test } from "@playwright/test";

import { logIn } from "./support/session";
import { createRecipes, createUser, uniqueToken } from "./support/stack";

test("keyword search shows at most five matches and how long it took", async ({ page }) => {
  const token = uniqueToken();
  createRecipes(Array.from({ length: 7 }, (_, i) => ({ name: `Bowl ${token} ${i}`, ingredients: ["1 cup rice"] })));
  await logIn(page, createUser());

  await page.getByText("Keyword search", { exact: true }).click();
  await expect(page.getByRole("radio", { name: "Keyword search" })).toBeChecked();
  await page.getByRole("searchbox").fill(token);
  await page.getByRole("button", { name: "Search" }).click();

  await expect(page.getByTestId("recipe-card")).toHaveCount(5);
  await expect(page.getByTestId("search-elapsed")).toHaveText(/^5 results in \d+(\.\d)? (ms|s)$/);
});

test("keyword search matches ingredients and says when nothing matches", async ({ page }) => {
  const token = uniqueToken();
  createRecipes([{ name: `Weeknight Pasta ${token}`, ingredients: [`2 cloves garlic${token}`] }]);
  await logIn(page, createUser());
  await page.getByText("Keyword search", { exact: true }).click();
  await expect(page.getByRole("radio", { name: "Keyword search" })).toBeChecked();

  await page.getByRole("searchbox").fill(`garlic${token}`);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByTestId("recipe-card")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: `Weeknight Pasta ${token}` })).toBeVisible();

  await page.getByRole("searchbox").fill(`nothing${token}`);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText(`No recipes have “nothing${token}” in their name or ingredients.`)).toBeVisible();
});

test("AI search returns three described recipes and the time it took", async ({ page }) => {
  // The first AI search in a fresh worker loads the embedding model.
  test.setTimeout(180_000);
  const token = uniqueToken();
  createRecipes([0, 1, 2].map((i) => ({ name: `Stub Candidate ${token} ${i}`, embedded: true })));
  await logIn(page, createUser());

  await expect(page.getByRole("radio", { name: "AI search" })).toBeChecked();
  await page.getByRole("searchbox").fill("something warm and high in fibre");
  await page.getByRole("button", { name: "Ask" }).click();

  await expect(page.getByText("Finding recipes for you…")).toBeVisible();
  await expect(page.getByTestId("recipe-card")).toHaveCount(3, { timeout: 150_000 });
  await expect(page.getByText(/^Stub pick: /)).toHaveCount(3);
  await expect(page.getByTestId("search-elapsed")).toHaveText(/^Found in \d+(\.\d)? (ms|s)$/);
});
