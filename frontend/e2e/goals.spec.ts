import { expect, test } from "@playwright/test";

import { logIn } from "./support/session";
import { createUser } from "./support/stack";

test("nutrition goals are saved and still there after a reload", async ({ page }) => {
  await logIn(page, createUser());
  await page.getByRole("link", { name: "Goals" }).click();

  await page.getByLabel(/Protein/).fill("120");
  await page.getByLabel(/Fiber/).fill("30");
  await page.getByRole("button", { name: "Save goals" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel(/Protein/)).toHaveValue("120");
  await expect(page.getByLabel(/Fiber/)).toHaveValue("30");
  await expect(page.getByLabel(/Calories/)).toHaveValue("");
});

test("a failed save says so and lets you try again", async ({ page }) => {
  await logIn(page, createUser());
  await page.getByRole("link", { name: "Goals" }).click();
  await page.getByLabel(/Protein/).fill("120");

  // Drop the connection on the save only, as if the network went away mid-request.
  await page.route("**/api/profile", (route) =>
    route.request().method() === "PUT" ? route.abort("internetdisconnected") : route.fallback(),
  );
  await page.getByRole("button", { name: "Save goals" }).click();

  await expect(page.getByText("Couldn’t reach the server. Try again.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save goals" })).toBeEnabled();
});
