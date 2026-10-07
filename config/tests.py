import logging

from django.test import SimpleTestCase

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
