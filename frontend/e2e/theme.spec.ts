import { expect, test } from "@playwright/test";

test("the theme can be pinned to dark or light, survives a reload, and returns to the system setting", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/login");
  const html = page.locator("html");
  const toggle = page.getByRole("button", { name: /^Theme:/ });

  await expect(toggle).toHaveAccessibleName("Theme: System. Switch to Light");
  await toggle.click();
  await expect(html).toHaveAttribute("data-theme", "light");
  await toggle.click();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(20, 20, 20)");

  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(20, 20, 20)");

  await toggle.click();
  await expect(html).not.toHaveAttribute("data-theme");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(246, 244, 239)");
});
