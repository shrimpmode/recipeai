"""The Claude adapter against a local HTTP server standing in for the Messages
API at the network boundary: the real SDK runs, only the far end is fake."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anthropic
from django.conf import settings
from django.test import SimpleTestCase

from queries.services.generation import ClaudePicker
from queries.services.resolution import PermanentFailure, Pick, UnusablePicks


class _FakeMessagesApi(BaseHTTPRequestHandler):
    status = 200
    body: dict = {}
    delay = 0.0
    requests: list[dict] = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        type(self).requests.append(json.loads(self.rfile.read(length)))
        time.sleep(self.delay)
        payload = json.dumps(self.body).encode()
        try:
            self.send_response(self.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except BrokenPipeError:
            pass  # the client timed out first (test_a_slow_response_times_out_as_retryable)

    def log_message(self, *args):
        pass


def _message(text: str) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5-20251001",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def _error(status: int, kind: str) -> tuple[int, dict]:
    return status, {"type": "error", "error": {"type": kind, "message": "nope"}}


SHORTLIST = [{"recipe_id": 1, "recipe_name": "Oats"}, {"recipe_id": 2, "recipe_name": "Salad"}]


class ClaudePickerTests(SimpleTestCase):
    server: ThreadingHTTPServer

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeMessagesApi)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)

    def setUp(self):
        _FakeMessagesApi.status, _FakeMessagesApi.body, _FakeMessagesApi.delay = 200, {}, 0.0
        _FakeMessagesApi.requests = []
        client = anthropic.Anthropic(
            api_key="test-key", base_url=f"http://127.0.0.1:{self.server.server_port}", max_retries=0, timeout=2
        )
        self.picker = ClaudePicker(client=client)

    def _respond(self, status: int, body: dict) -> None:
        _FakeMessagesApi.status, _FakeMessagesApi.body = status, body

    def test_parses_picks_even_inside_a_code_fence(self):
        self._respond(200, _message('```json\n[{"recipe_id": 2, "description": "Light."}]\n```'))

        picks = self.picker.pick("something light", SHORTLIST, count=1)

        self.assertEqual(picks, [Pick(recipe_id=2, description="Light.")])
        sent = _FakeMessagesApi.requests[0]
        self.assertIn("exactly 1 objects", sent["system"])
        self.assertEqual(json.loads(sent["messages"][0]["content"])["candidates"], SHORTLIST)

    def test_unparseable_or_malformed_answers_are_unusable(self):
        for text in ("Here are some recipes!", '{"recipe_id": 1}', '[{"recipe_id": "1", "description": "x"}]'):
            with self.subTest(text=text):
                self._respond(200, _message(text))
                with self.assertRaises(UnusablePicks):
                    self.picker.pick("x", SHORTLIST, count=1)

    def test_requests_claude_will_never_accept_fail_permanently(self):
        for status, kind in [(400, "invalid_request_error"), (401, "authentication_error"), (403, "permission_error")]:
            with self.subTest(status=status):
                self._respond(*_error(status, kind))
                with self.assertRaises(PermanentFailure):
                    self.picker.pick("x", SHORTLIST, count=1)

    def test_rate_limits_overload_and_server_errors_stay_retryable(self):
        for status, kind in [(429, "rate_limit_error"), (500, "api_error"), (529, "overloaded_error")]:
            with self.subTest(status=status):
                self._respond(*_error(status, kind))
                with self.assertRaises(anthropic.APIStatusError) as caught:
                    self.picker.pick("x", SHORTLIST, count=1)
                self.assertNotIsInstance(caught.exception, PermanentFailure)

    def test_a_slow_response_times_out_as_retryable(self):
        _FakeMessagesApi.delay = 0.5
        client = anthropic.Anthropic(
            api_key="k", base_url=f"http://127.0.0.1:{self.server.server_port}", max_retries=0, timeout=0.1
        )

        with self.assertRaises(anthropic.APITimeoutError):
            ClaudePicker(client=client).pick("x", SHORTLIST, count=1)

    def test_default_client_has_a_timeout_and_no_sdk_retries(self):
        client = ClaudePicker()._client

        self.assertEqual(client.max_retries, 0)
        self.assertEqual(client.timeout, settings.CLAUDE_TIMEOUT_SECONDS)
