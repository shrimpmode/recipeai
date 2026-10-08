"""Keyword search without AI (`search_recipes` and the `/search/` endpoint),
run against the real Postgres database. Nothing is mocked: this path calls
neither the embedding model nor Claude."""

from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import TestCase

from recipes.models import Recipe
from recipes.services.keyword_search import MAX_TERMS, matching_recipes, search_recipes


def _recipe(name: str, ingredients: list[str] | None = None, **overrides) -> Recipe:
    fields = {
        "recipe_name": name,
        "source_url": f"https://example.com/{name.lower().replace(' ', '-')}",
        "servings": 2,
        "ingredient_lines": ingredients or [],
        "calories_per_serving": 300,
    }
    return Recipe.objects.create(**(fields | overrides))


def _names(recipes: list[Recipe]) -> list[str]:
    return [r.recipe_name for r in recipes]


class SearchRecipesTests(TestCase):
    def test_matches_name_case_insensitively(self):
        _recipe("Lemon Chicken")
        _recipe("Beef Stew")

        self.assertEqual(_names(search_recipes("lemon", limit=5)), ["Lemon Chicken"])

    def test_matches_ingredients(self):
        _recipe("Weeknight Pasta", ["200g spaghetti", "2 cloves Garlic"])
        _recipe("Fruit Salad", ["1 apple"])

        self.assertEqual(_names(search_recipes("garlic", limit=5)), ["Weeknight Pasta"])

    def test_every_term_must_match_somewhere(self):
        _recipe("Chicken Soup", ["1 lemon"])
        _recipe("Chicken Curry", ["1 onion"])

        self.assertEqual(_names(search_recipes("chicken lemon", limit=5)), ["Chicken Soup"])

    def test_name_matches_rank_before_ingredient_only_matches(self):
        _recipe("Apple Pie Spice Mix", ["cinnamon"])
        _recipe("Baked Apple Crumble", ["2 apples"])
        _recipe("Autumn Salad", ["1 apple", "walnuts"])

        self.assertEqual(
            _names(search_recipes("apple", limit=5)),
            ["Apple Pie Spice Mix", "Baked Apple Crumble", "Autumn Salad"],
        )

    def test_returns_at_most_the_limit(self):
        for i in range(7):
            _recipe(f"Oat Bowl {i}")

        self.assertEqual(len(search_recipes("oat", limit=5)), 5)

    def test_recipes_without_embeddings_are_found(self):
        _recipe("Not Yet Embedded Tofu", embedding=None)

        self.assertEqual(_names(search_recipes("tofu", limit=5)), ["Not Yet Embedded Tofu"])

    def test_like_wildcards_are_matched_literally(self):
        _recipe("100% Rye Bread")
        _recipe("Rye Crackers")

        self.assertEqual(_names(search_recipes("100%", limit=5)), ["100% Rye Bread"])

    def test_blank_query_returns_nothing(self):
        _recipe("Anything")

        self.assertEqual(search_recipes("   ", limit=5), [])

    def test_terms_beyond_the_cap_are_ignored(self):
        _recipe("Rice Bowl")
        filler = " ".join(["rice"] * MAX_TERMS)

        self.assertEqual(_names(search_recipes(f"{filler} nonexistent", limit=5)), ["Rice Bowl"])


class TrigramIndexTests(TestCase):
    """Guards the coupling between the indexed expressions and the SQL the ORM
    generates: if they drift apart, Postgres silently falls back to a full scan."""

    def _plan(self, query: str) -> str:
        with transaction.atomic(), connection.cursor() as cursor:
            # The test table is tiny, so the planner would scan it anyway; forbid that to see if the index is usable.
            cursor.execute("SET LOCAL enable_seqscan = off")
            return matching_recipes(query).explain()

    def test_searches_use_both_trigram_indexes(self):
        plan = self._plan("saffron rice")

        self.assertIn("recipe_name_trgm", plan)
        self.assertIn("recipe_ingredients_trgm", plan)


class KeywordSearchApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="pw12345!")

    def _search(self, q: str):
        return self.client.get("/api/search", {"q": q})

    def test_anonymous_user_is_rejected(self):
        self.assertEqual(self._search("oats").status_code, 401)

    def test_returns_at_most_five_results_with_elapsed_time(self):
        self.client.force_login(self.user)
        for i in range(7):
            _recipe(f"Oat Bowl {i}")

        response = self._search("oat")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["results"]), 5)
        self.assertEqual(body["query"], "oat")
        self.assertGreaterEqual(body["elapsed_ms"], 0)
        self.assertEqual(set(body["results"][0]), {"id", "recipe_name", "source_url", "image_url", *NUTRITION_FIELDS})

    def test_no_match_returns_an_empty_list(self):
        self.client.force_login(self.user)

        body = self._search("durian").json()

        self.assertEqual(body["results"], [])

    def test_blank_query_is_rejected(self):
        self.client.force_login(self.user)

        for q in ("", "   "):
            self.assertEqual(self._search(q).status_code, 422)


NUTRITION_FIELDS = {
    "calories_per_serving",
    "protein_g_per_serving",
    "carbs_g_per_serving",
    "fat_g_per_serving",
    "fiber_g_per_serving",
    "sugar_g_per_serving",
    "sodium_mg_per_serving",
}
