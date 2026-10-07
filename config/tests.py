import logging

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from config.logging import KeyValueFormatter


def _record(**extra) -> logging.LogRecord:
    record = logging.makeLogRecord({"name": "queries.tasks", "levelname": "ERROR", "msg": "query_failed"})
    record.__dict__.update(extra)
    return record


class KeyValueFormatterTests(SimpleTestCase):
    def test_appends_extras_as_key_value_pairs(self):
        line = KeyValueFormatter("%(levelname)s %(name)s %(message)s").format(
            _record(query_request_id=21, error="bad key")
        )

        self.assertEqual(line, "ERROR queries.tasks query_failed query_request_id=21 error='bad key'")

    def test_extras_come_before_the_traceback(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            import sys

            record = _record(query_request_id=21)
            record.exc_info = sys.exc_info()

        line = KeyValueFormatter("%(message)s").format(record)

        first_line, traceback = line.split("\n", 1)
        self.assertEqual(first_line, "query_failed query_request_id=21")
        self.assertIn("RuntimeError: boom", traceback)


class ManualTests(TestCase):
    def test_staff_can_read_the_manual(self):
        self.client.force_login(User.objects.create_user(username="ops", password="pw12345!", is_staff=True))

        response = self.client.get(reverse("manual"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Nutrition RAG Manual</title>")

    def test_non_staff_user_is_sent_to_the_admin_login(self):
        self.client.force_login(User.objects.create_user(username="alex", password="pw12345!"))

        response = self.client.get(reverse("manual"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.headers["Location"])

    def test_anonymous_user_is_sent_to_the_admin_login(self):
        response = self.client.get(reverse("manual"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.headers["Location"])
