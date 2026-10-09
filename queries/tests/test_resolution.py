"""The AI search resolution module through its interface, with fake adapters
passed in and the real Postgres + pgvector database."""

from django.contrib.auth.models import User
from django.test import TestCase

from accounts.models import Profile
from queries.services.resolution import Pick, Resolver, UnusablePicks
from queries.tests.fakes import FakeEmbedder, FakePicker
from queries.tests.recipes import embedding, make_recipe


class ResolverTests(TestCase):
    def setUp(self):
        self.embedder, self.picker = FakeEmbedder(), FakePicker()
        self.resolver = Resolver(
            embedder=self.embedder, picker=self.picker, candidate_count=15, shortlist_size=5, result_count=3
        )

    def _shortlist_ids(self) -> list[int]:
        return [c["recipe_id"] for c in self.picker.shortlists[-1]]

    def test_returns_the_picks_in_order_with_their_descriptions(self):
        recipes = [make_recipe(recipe_name=f"R{i}", source_url=f"https://example.com/{i}") for i in range(4)]
        self.picker.script = [[Pick(recipes[2].id, "Third."), Pick(recipes[0].id, "First."), Pick(recipes[1].id, "x")]]

        results = self.resolver.resolve("anything", profile=None)

        self.assertEqual([r["recipe_id"] for r in results], [recipes[2].id, recipes[0].id, recipes[1].id])
        self.assertEqual(results[0]["description"], "Third.")
        self.assertEqual(results[0]["source_url"], "https://example.com/2")

    def test_without_goals_the_shortlist_is_in_similarity_order(self):
        far = make_recipe(recipe_name="Far", embedding=embedding(-1.0))
        near = make_recipe(recipe_name="Near", embedding=embedding(1.0))
        middle = make_recipe(recipe_name="Middle", embedding=[1.0, -1.0] * 192)
        self.embedder.vector = embedding(1.0)

        self.resolver.resolve("anything", profile=None)

        self.assertEqual(self._shortlist_ids(), [near.id, middle.id, far.id])

    def test_goals_rerank_the_shortlist_by_nutrition_closeness(self):
        user = User.objects.create_user(username="alex", password="pw12345!")
        # Daily fiber target of 30 g -> 10 g per meal under the 3-meals-a-day assumption.
        profile = Profile.objects.create(user=user, fiber_target_g=30)
        far = make_recipe(recipe_name="Far fiber", fiber_g_per_serving=1)
        close = make_recipe(recipe_name="Close fiber", fiber_g_per_serving=10)
        mid = make_recipe(recipe_name="Mid fiber", fiber_g_per_serving=6)

        self.resolver.resolve("high fiber", profile)

        self.assertEqual(self._shortlist_ids(), [close.id, mid.id, far.id])

    def test_recipes_without_embeddings_are_never_shortlisted(self):
        embedded = [make_recipe(recipe_name=f"E{i}", source_url=f"https://example.com/{i}") for i in range(3)]
        pending = make_recipe(recipe_name="Not yet embedded", embedding=None)

        self.resolver.resolve("anything", profile=None)

        self.assertNotIn(pending.id, self._shortlist_ids())
        self.assertEqual(set(self._shortlist_ids()), {r.id for r in embedded})

    def test_picks_outside_the_shortlist_or_repeated_are_unusable(self):
        recipes = [make_recipe(recipe_name=f"R{i}") for i in range(3)]
        self.picker.script = [[Pick(recipes[0].id, "a"), Pick(recipes[0].id, "again"), Pick(999_999, "invented")]]

        with self.assertRaises(UnusablePicks):
            self.resolver.resolve("anything", profile=None)

    def test_extra_picks_beyond_the_result_count_are_dropped(self):
        recipes = [make_recipe(recipe_name=f"R{i}") for i in range(4)]
        self.picker.script = [[Pick(r.id, "fine") for r in recipes]]

        self.assertEqual(len(self.resolver.resolve("anything", profile=None)), 3)
