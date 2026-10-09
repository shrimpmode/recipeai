"""The query request lifecycle (queries/models.py): transitions, finish time and
the deadline, tested on database rows with no Celery or HTTP in the way."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.utils import timezone

from queries.apps import QueriesConfig
from queries.models import QueryRequest
from queries.tasks import worst_case_seconds

Status = QueryRequest.Status


class QueryRequestLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="sam", password="pw12345!")

    def _request(self, **fields) -> QueryRequest:
        return QueryRequest.objects.create(user=self.user, prompt="lunch", **fields)

    def _overdue(self) -> QueryRequest:
        return self._request(expires_at=timezone.now() - timedelta(seconds=1))

    @override_settings(QUERY_DEADLINE_SECONDS=90)
    def test_a_new_request_is_stamped_with_the_deadline(self):
        before = timezone.now()

        query_request = self._request()

        self.assertAlmostEqual((query_request.deadline - before).total_seconds(), 90, delta=2)

    def test_success_records_results_and_finish_time(self):
        query_request = self._request()

        self.assertTrue(query_request.start())
        self.assertTrue(query_request.succeed([{"recipe_id": 1}]))

        stored = QueryRequest.objects.get(pk=query_request.pk)
        self.assertEqual((stored.status, stored.results), (Status.DONE, [{"recipe_id": 1}]))
        self.assertTrue(stored.is_finished)
        assert stored.finished_at is not None and stored.elapsed_seconds is not None
        self.assertGreaterEqual(stored.elapsed_seconds, 0)

    def test_elapsed_time_is_none_until_finished_and_ignores_later_saves(self):
        query_request = self._request()
        self.assertIsNone(query_request.elapsed_seconds)
        query_request.fail("boom")
        elapsed = query_request.elapsed_seconds

        query_request.prompt = "edited in the admin"
        query_request.save()

        self.assertEqual(QueryRequest.objects.get(pk=query_request.pk).elapsed_seconds, elapsed)

    def test_a_finished_request_cannot_be_overwritten(self):
        query_request = self._request()
        query_request.fail("boom")
        stale_copy = QueryRequest.objects.get(pk=query_request.pk)
        stale_copy.status = Status.RUNNING  # what a stale in-memory copy would believe

        self.assertFalse(stale_copy.succeed([{"recipe_id": 1}]))
        self.assertFalse(stale_copy.start())

        stored = QueryRequest.objects.get(pk=query_request.pk)
        self.assertEqual((stored.status, stored.results), (Status.ERROR, None))
        self.assertEqual(stale_copy.status, Status.ERROR)  # refreshed when the transition lost

    def test_an_overdue_request_expires_as_an_error(self):
        query_request = self._overdue()

        self.assertTrue(query_request.expire_if_overdue())

        stored = QueryRequest.objects.get(pk=query_request.pk)
        self.assertEqual((stored.status, stored.error_message), (Status.ERROR, QueryRequest.EXPIRED_MESSAGE))
        self.assertFalse(stored.expire_if_overdue())  # already ended

    def test_an_expired_request_finished_at_its_deadline_not_when_it_was_noticed(self):
        query_request = self._request()
        QueryRequest.objects.filter(pk=query_request.pk).update(
            created_at=timezone.now() - timedelta(days=30), expires_at=timezone.now() - timedelta(days=30, seconds=-150)
        )
        query_request.refresh_from_db()

        query_request.expire_if_overdue()

        self.assertAlmostEqual(QueryRequest.objects.get(pk=query_request.pk).elapsed_seconds or 0, 150, delta=1)

    def test_a_request_within_its_deadline_is_left_alone(self):
        query_request = self._request()

        self.assertFalse(query_request.expire_if_overdue())
        self.assertEqual(query_request.status, Status.PENDING)

    def test_past_the_deadline_a_request_can_only_end_as_an_error(self):
        for transition in ("start", "succeed"):
            with self.subTest(transition=transition):
                query_request = self._overdue()
                args = ([{"recipe_id": 1}],) if transition == "succeed" else ()

                self.assertFalse(getattr(query_request, transition)(*args))
                self.assertEqual(QueryRequest.objects.get(pk=query_request.pk).status, Status.ERROR)

    @override_settings(QUERY_DEADLINE_SECONDS=150)
    def test_a_row_without_a_stamped_deadline_falls_back_to_created_at(self):
        query_request = self._request()
        QueryRequest.objects.filter(pk=query_request.pk).update(
            expires_at=None, created_at=timezone.now() - timedelta(seconds=151)
        )

        self.assertTrue(QueryRequest.objects.get(pk=query_request.pk).expire_if_overdue())


class DeadlineConfigTests(TestCase):
    @override_settings(QUERY_TASK_MAX_RETRIES=3, AI_SEARCH_MODEL_TIMEOUT_SECONDS=30, QUERY_RETRY_BACKOFF_SECONDS=2)
    def test_worst_case_is_every_attempt_timing_out_plus_every_backoff_ceiling(self):
        self.assertEqual(worst_case_seconds(), 4 * 30 + (2 + 4 + 8))

    def test_startup_rejects_a_deadline_shorter_than_the_retry_worst_case(self):
        config = QueriesConfig.create("queries")
        with (
            override_settings(QUERY_DEADLINE_SECONDS=worst_case_seconds() - 1),
            self.assertRaises(ImproperlyConfigured),
        ):
            config.ready()
        with override_settings(QUERY_DEADLINE_SECONDS=worst_case_seconds()):
            config.ready()
