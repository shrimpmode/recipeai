"""The AI search API (`POST /api/queries` + `GET /api/queries/{id}`) and the
Celery task behind it: lifecycle, retries and what the user gets to see.

Celery runs eager, so the whole pipeline (embed -> retrieve -> rerank ->
pick) executes inside the submit request, retries included (eager retries run
at once, ignoring the countdown). The embedder and the picker are the fake
adapters, selected through settings; nothing is patched.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from queries.models import QueryRequest
from queries.services.resolution import PermanentFailure, Pick
from queries.tasks import resolve_query, retry_delay_seconds
from queries.tests.fakes import fake_adapters, use_fake_adapters
from queries.tests.recipes import make_recipe


@use_fake_adapters
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=False)
class QueryFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="pw12345!")
        self.embedder, self.picker = fake_adapters()
        self.recipes = [make_recipe(recipe_name=f"Recipe {i}", source_url=f"https://example.com/{i}") for i in range(3)]

    def _submit(self, prompt: str = "something high fiber"):
        return self.client.post("/api/queries", {"prompt": prompt}, content_type="application/json")

    def _only_request(self) -> QueryRequest:
        return QueryRequest.objects.get(user=self.user)

    def test_anonymous_user_is_rejected(self):
        response = self._submit()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(QueryRequest.objects.count(), 0)

    def test_submit_returns_three_described_results(self):
        self.client.force_login(self.user)

        response = self._submit()

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "done")
        self.assertEqual({r["recipe_id"] for r in body["results"]}, {r.id for r in self.recipes})
        for result in body["results"]:
            self.assertTrue(result["description"].startswith("Picked "))
            self.assertIn("calories_per_serving", result)
            self.assertIn("source_url", result)

    def test_poll_status_endpoint_reflects_final_state(self):
        self.client.force_login(self.user)
        self._submit()

        response = self.client.get(f"/api/queries/{self._only_request().id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "done")
        self.assertEqual(len(body["results"]), settings.RESULT_COUNT)
        self.assertGreaterEqual(body["elapsed_seconds"], 0)

    def test_succeeds_after_a_transient_failure(self):
        self.client.force_login(self.user)
        self.picker.script = [RuntimeError("overloaded")]

        self._submit()

        self.assertEqual(self._only_request().status, QueryRequest.Status.DONE)
        self.assertEqual(len(self.picker.shortlists), 2)

    def test_repeated_transient_failures_retry_then_mark_error(self):
        self.client.force_login(self.user)
        self.picker.script = [RuntimeError("claude unavailable")] * (settings.QUERY_TASK_MAX_RETRIES + 1)

        with self.assertLogs("queries.tasks", level="WARNING") as logs:
            self._submit()

        query_request = self._only_request()
        self.assertEqual(query_request.status, QueryRequest.Status.ERROR)
        self.assertIn("claude unavailable", query_request.error_message)
        self.assertEqual(len(self.picker.shortlists), settings.QUERY_TASK_MAX_RETRIES + 1)
        retries = [r for r in logs.records if r.levelname == "WARNING"]
        errors = [r for r in logs.records if r.levelname == "ERROR"]
        self.assertEqual([r.attempt for r in retries], [1, 2, 3])  # type: ignore[attr-defined]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].query_request_id, query_request.id)  # type: ignore[attr-defined]

        body = self.client.get(f"/api/queries/{query_request.id}").json()
        self.assertEqual(body["status"], "error")
        self.assertIsNone(body["results"])
        self.assertNotIn("unavailable", str(body))  # provider error text stays in the logs

    def test_permanent_failure_is_not_retried(self):
        self.client.force_login(self.user)
        self.picker.script = [PermanentFailure("Claude rejected the request: HTTP 401")]

        with self.assertLogs("queries.tasks", level="WARNING") as logs:
            self._submit()

        query_request = self._only_request()
        self.assertEqual(query_request.status, QueryRequest.Status.ERROR)
        self.assertEqual(len(self.picker.shortlists), 1)
        self.assertEqual([r.levelname for r in logs.records], ["ERROR"])
        self.assertFalse(logs.records[0].retryable)  # type: ignore[attr-defined]

    def test_unusable_picks_are_retried(self):
        self.client.force_login(self.user)
        self.picker.script = [[Pick(999_999, "invented")]]

        self._submit()

        self.assertEqual(self._only_request().status, QueryRequest.Status.DONE)
        self.assertEqual(len(self.picker.shortlists), 2)

    def test_a_finished_request_is_not_resolved_again(self):
        query_request = QueryRequest.objects.create(
            user=self.user, prompt="again", status=QueryRequest.Status.DONE, results=[]
        )

        resolve_query.delay(query_request.id)  # e.g. the broker delivers the message twice

        query_request.refresh_from_db()
        self.assertEqual(query_request.results, [])
        self.assertEqual(self.picker.shortlists, [])

    def test_a_request_deleted_while_queued_is_skipped(self):
        query_request = QueryRequest.objects.create(user=self.user, prompt="gone")
        query_request_id = query_request.id
        query_request.delete()

        with self.assertLogs("queries.tasks", level="INFO") as logs:
            resolve_query.delay(query_request_id)

        self.assertEqual([r.getMessage() for r in logs.records], ["query_request_gone"])
        self.assertEqual(self.picker.shortlists, [])

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


class RetryDelayTests(TestCase):
    def test_backoff_doubles_with_jitter_inside_each_window(self):
        base = settings.QUERY_RETRY_BACKOFF_SECONDS
        for retries in range(4):
            ceiling = base * 2**retries
            for _ in range(50):
                self.assertTrue(ceiling / 2 <= retry_delay_seconds(retries) <= ceiling)
