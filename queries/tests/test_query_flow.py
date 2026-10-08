"""Seam 1: the AI search API (`POST /api/queries` + `GET /api/queries/{id}`).

Celery runs eager (see override_settings below) so the whole pipeline
(embed -> retrieve -> optionally rerank by goals -> generate) executes
synchronously inside the submit request. The only things mocked are
the external/heavyweight boundaries: the local embedding model
(`embed_query`) and the Claude API (`select_and_describe`).
"""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from accounts.models import Profile
from queries.models import QueryRequest
from recipes.models import Recipe


def _embedding(seed: float) -> list[float]:
    return [seed] * settings.EMBEDDING_DIMENSIONS


def _make_recipe(**overrides) -> Recipe:
    defaults = {
        "recipe_name": "Recipe",
        "source_url": "https://example.com/recipe",
        "servings": 2,
        "ingredient_lines": ["stuff"],
        "diet_labels": [],
        "health_labels": [],
        "cautions": [],
        "cuisine_type": [],
        "meal_type": [],
        "dish_type": [],
        "calories_per_serving": 300,
        "protein_g_per_serving": 10,
        "carbs_g_per_serving": 30,
        "fat_g_per_serving": 10,
        "fiber_g_per_serving": 5,
        "sugar_g_per_serving": 5,
        "sodium_mg_per_serving": 200,
        "embedding": _embedding(0.1),
    }
    defaults.update(overrides)
    return Recipe.objects.create(**defaults)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class QueryFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="pw12345!")

    def _submit(self, prompt: str):
        return self.client.post("/api/queries", {"prompt": prompt}, content_type="application/json")

    def test_anonymous_user_is_redirected_to_login(self):
        response = self._submit("high fiber")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(QueryRequest.objects.count(), 0)

    @patch("queries.services.generation.select_and_describe")
    @patch("queries.services.retrieval.embed_query")
    def test_submit_query_returns_three_results(self, mock_embed_query, mock_select_and_describe):
        self.client.force_login(self.user)
        recipes = [
            _make_recipe(
                recipe_name=f"Recipe {i}",
                source_url=f"https://example.com/{i}",
                embedding=_embedding(0.1 * i),
            )
            for i in range(5)
        ]
        mock_embed_query.return_value = _embedding(0.0)
        mock_select_and_describe.return_value = [
            {"recipe_id": recipes[0].id, "description": "Great fit."},
            {"recipe_id": recipes[1].id, "description": "Also good."},
            {"recipe_id": recipes[2].id, "description": "Solid choice."},
        ]

        response = self._submit("something high fiber")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "done")
        query_request = QueryRequest.objects.get(user=self.user)
        self.assertEqual(query_request.status, QueryRequest.Status.DONE)
        results = query_request.results
        assert results is not None
        self.assertEqual(len(results), 3)
        self.assertEqual(
            {r["recipe_id"] for r in results},
            {recipes[0].id, recipes[1].id, recipes[2].id},
        )
        for result in results:
            self.assertIn("description", result)
            self.assertIn("calories_per_serving", result)
            self.assertIn("source_url", result)

    @patch("queries.services.generation.select_and_describe")
    @patch("queries.services.retrieval.embed_query")
    def test_no_goals_skips_reranking_and_uses_similarity_order(self, mock_embed_query, mock_select_and_describe):
        self.client.force_login(self.user)
        # No Profile created for self.user at all.
        near = _make_recipe(recipe_name="Near", embedding=_embedding(0.0))
        middle = _make_recipe(recipe_name="Middle", embedding=_embedding(2.5))
        far = _make_recipe(recipe_name="Far", embedding=_embedding(5.0))
        mock_embed_query.return_value = _embedding(0.0)
        mock_select_and_describe.return_value = [
            {"recipe_id": near.id, "description": "x"},
            {"recipe_id": middle.id, "description": "y"},
            {"recipe_id": far.id, "description": "z"},
        ]

        self._submit("anything")

        candidates_sent = mock_select_and_describe.call_args.args[1]
        candidate_ids_in_order = [c["recipe_id"] for c in candidates_sent]
        self.assertEqual(candidate_ids_in_order[0], near.id)
        self.assertEqual(candidate_ids_in_order[-1], far.id)

    @patch("queries.services.generation.select_and_describe")
    @patch("queries.services.retrieval.embed_query")
    def test_goals_set_reranks_candidates_by_nutrition_closeness(self, mock_embed_query, mock_select_and_describe):
        self.client.force_login(self.user)
        # Daily fiber target of 30g -> ~10g/meal under the 3-meals/day assumption.
        Profile.objects.create(user=self.user, fiber_target_g=30)

        close_match = _make_recipe(recipe_name="Close fiber", fiber_g_per_serving=10, embedding=_embedding(0.0))
        mid_match = _make_recipe(recipe_name="Mid fiber", fiber_g_per_serving=6, embedding=_embedding(0.0))
        far_match = _make_recipe(recipe_name="Far fiber", fiber_g_per_serving=1, embedding=_embedding(0.0))

        mock_embed_query.return_value = _embedding(0.0)
        mock_select_and_describe.return_value = [
            {"recipe_id": close_match.id, "description": "x"},
            {"recipe_id": mid_match.id, "description": "y"},
            {"recipe_id": far_match.id, "description": "z"},
        ]

        self._submit("high fiber")

        candidates_sent = mock_select_and_describe.call_args.args[1]
        candidate_ids_in_order = [c["recipe_id"] for c in candidates_sent]
        self.assertEqual(candidate_ids_in_order[0], close_match.id)
        self.assertIn(far_match.id, candidate_ids_in_order)

    @patch("queries.services.generation.select_and_describe")
    @patch("queries.services.retrieval.embed_query")
    def test_recipes_without_embeddings_are_never_candidates(self, mock_embed_query, mock_select_and_describe):
        self.client.force_login(self.user)
        embedded = [_make_recipe(recipe_name=f"Embedded {i}", source_url=f"https://example.com/{i}") for i in range(3)]
        pending = _make_recipe(recipe_name="Not yet embedded", embedding=None)
        mock_embed_query.return_value = _embedding(0.0)
        mock_select_and_describe.return_value = [{"recipe_id": r.id, "description": "x"} for r in embedded]

        self._submit("anything")

        candidate_ids = {c["recipe_id"] for c in mock_select_and_describe.call_args.args[1]}
        self.assertNotIn(pending.id, candidate_ids)
        self.assertEqual(QueryRequest.objects.get(user=self.user).status, QueryRequest.Status.DONE)

    @patch("queries.tasks.time.sleep")
    @patch("queries.services.generation.select_and_describe")
    @patch("queries.services.retrieval.embed_query")
    def test_repeated_failures_retry_then_mark_error(self, mock_embed_query, mock_select_and_describe, mock_sleep):
        self.client.force_login(self.user)
        _make_recipe()
        mock_embed_query.return_value = _embedding(0.0)
        mock_select_and_describe.side_effect = RuntimeError("openai/claude unavailable")

        self._submit("anything")

        query_request = QueryRequest.objects.get(user=self.user)
        self.assertEqual(query_request.status, QueryRequest.Status.ERROR)
        self.assertIn("openai/claude unavailable", query_request.error_message)
        self.assertEqual(mock_select_and_describe.call_count, settings.QUERY_TASK_MAX_RETRIES + 1)
        self.assertEqual(mock_sleep.call_count, settings.QUERY_TASK_MAX_RETRIES)

        body = self.client.get(f"/api/queries/{query_request.id}").json()
        self.assertEqual(body["status"], "error")
        self.assertIsNone(body["results"])
        self.assertNotIn("unavailable", str(body))  # provider error text stays in the logs

    @patch("queries.tasks.time.sleep")
    @patch("queries.services.generation.select_and_describe")
    @patch("queries.services.retrieval.embed_query")
    def test_failed_query_is_logged_with_its_id_and_cause(self, mock_embed_query, mock_select_and_describe, _sleep):
        self.client.force_login(self.user)
        _make_recipe()
        mock_embed_query.return_value = _embedding(0.0)
        mock_select_and_describe.side_effect = RuntimeError("API key is invalid")

        with self.assertLogs("queries.tasks", level="WARNING") as logs:
            self._submit("anything")

        query_request = QueryRequest.objects.get(user=self.user)
        retries = [r for r in logs.records if r.levelname == "WARNING"]
        errors = [r for r in logs.records if r.levelname == "ERROR"]
        self.assertEqual(len(retries), settings.QUERY_TASK_MAX_RETRIES)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].query_request_id, query_request.id)  # type: ignore[attr-defined]
        assert errors[0].exc_info is not None
        self.assertIn("API key is invalid", str(errors[0].exc_info[1]))

    @patch("queries.services.generation.select_and_describe")
    @patch("queries.services.retrieval.embed_query")
    def test_succeeds_after_a_transient_failure(self, mock_embed_query, mock_select_and_describe):
        self.client.force_login(self.user)
        recipes = [_make_recipe(recipe_name=f"Recipe {i}", source_url=f"https://example.com/{i}") for i in range(3)]
        mock_embed_query.return_value = _embedding(0.0)
        mock_select_and_describe.side_effect = [
            RuntimeError("transient"),
            [{"recipe_id": r.id, "description": "Recovered fine."} for r in recipes],
        ]

        with patch("queries.tasks.time.sleep"):
            self._submit("anything")

        query_request = QueryRequest.objects.get(user=self.user)
        self.assertEqual(query_request.status, QueryRequest.Status.DONE)
        self.assertEqual(mock_select_and_describe.call_count, 2)

    @patch("queries.services.generation.select_and_describe")
    @patch("queries.services.retrieval.embed_query")
    def test_poll_status_endpoint_reflects_final_state(self, mock_embed_query, mock_select_and_describe):
        self.client.force_login(self.user)
        recipes = [_make_recipe(recipe_name=f"Recipe {i}", source_url=f"https://example.com/{i}") for i in range(3)]
        mock_embed_query.return_value = _embedding(0.0)
        mock_select_and_describe.return_value = [
            {"recipe_id": recipes[0].id, "description": "Tasty."},
            {"recipe_id": recipes[1].id, "description": "Also tasty."},
            {"recipe_id": recipes[2].id, "description": "Great too."},
        ]

        self._submit("anything")
        query_request = QueryRequest.objects.get(user=self.user)

        response = self.client.get(f"/api/queries/{query_request.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "done")
        self.assertEqual([r["description"] for r in body["results"]], ["Tasty.", "Also tasty.", "Great too."])
        self.assertGreaterEqual(body["elapsed_seconds"], 0)

    def test_cannot_poll_another_users_query(self):
        other_user = User.objects.create_user(username="other", password="pw12345!")
        query_request = QueryRequest.objects.create(user=other_user, prompt="secret", status=QueryRequest.Status.DONE)

        self.client.force_login(self.user)
        response = self.client.get(f"/api/queries/{query_request.id}")

        self.assertEqual(response.status_code, 404)

    def test_blank_prompt_is_rejected(self):
        self.client.force_login(self.user)

        for prompt in ("", "   "):
            self.assertEqual(self._submit(prompt).status_code, 400)
        self.assertEqual(QueryRequest.objects.count(), 0)
