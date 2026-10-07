import { defineConfig, devices } from "@playwright/test";

/**
 * E2E against the real stack (Next.js, Django, Celery, Postgres, Redis), with
 * only Claude stubbed. Start it first:
 *   docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build
 */
export default defineConfig({
  testDir: "./e2e",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // Flaky tests are bugs to fix, not to retry away.
  retries: 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
