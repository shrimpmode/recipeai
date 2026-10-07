import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import path from "node:path";

/**
 * Test data goes into the running stack's real database through Django's own
 * management commands, so each test creates exactly what it needs and nothing
 * depends on ordering or on the corpus being loaded.
 */
const REPO_ROOT = path.resolve(__dirname, "../../..");

function manage(args: string[], env: Record<string, string> = {}): string {
  const envFlags = Object.entries(env).flatMap(([key, value]) => ["-e", `${key}=${value}`]);
  return execFileSync("docker", ["compose", "exec", "-T", ...envFlags, "web", "python", "manage.py", ...args], {
    cwd: REPO_ROOT,
    encoding: "utf8",
  });
}

export type TestUser = { username: string; password: string };

export function uniqueToken(): string {
  return randomUUID().replaceAll("-", "").slice(0, 10);
}

export function createUser(): TestUser {
  const user = { username: `e2e_${uniqueToken()}`, password: `pw-${randomUUID()}` };
  manage(["createsuperuser", "--noinput", "--username", user.username, "--email", `${user.username}@example.com`], {
    DJANGO_SUPERUSER_PASSWORD: user.password,
  });
  return user;
}

export type SeedRecipe = { name: string; ingredients?: string[]; embedded?: boolean };

export function createRecipes(recipes: SeedRecipe[]): void {
  const script = `
import json, os
from django.conf import settings
from recipes.models import Recipe
for r in json.loads(os.environ["E2E_RECIPES"]):
    Recipe.objects.create(
        recipe_name=r["name"],
        source_url="https://example.com/e2e/" + r["name"].replace(" ", "-").lower(),
        servings=2,
        ingredient_lines=r.get("ingredients") or [],
        calories_per_serving=420, protein_g_per_serving=24, carbs_g_per_serving=48,
        fat_g_per_serving=14, fiber_g_per_serving=9, sugar_g_per_serving=6, sodium_mg_per_serving=380,
        embedding=[0.05] * settings.EMBEDDING_DIMENSIONS if r.get("embedded") else None,
    )
`;
  manage(["shell", "-c", script], { E2E_RECIPES: JSON.stringify(recipes) });
}

/** Removes everything the suite creates (users `e2e_*`, recipes under example.com/e2e/), cascading their data. */
export function deleteTestData(): void {
  manage([
    "shell",
    "-c",
    `
from django.contrib.auth.models import User
from recipes.models import Recipe
Recipe.objects.filter(source_url__startswith="https://example.com/e2e/").delete()
User.objects.filter(username__startswith="e2e_").delete()
`,
  ]);
}
