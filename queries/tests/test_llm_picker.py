"""The LLM picker against local HTTP servers standing in for each provider's API
at the network boundary: Pydantic AI and the real provider SDKs run, only the
far end is fake. Every provider in model_providers must pass the same contract."""

import json
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel

from queries.services.generation import LLMPicker
from queries.services.model_providers import ModelSpec, build_model
from queries.services.resolution import PermanentFailure, Pick, UnusablePicks

SHORTLIST = [{"recipe_id": 1, "recipe_name": "Oats"}, {"recipe_id": 2, "recipe_name": "Salad"}]


class _FakeProviderApi(BaseHTTPRequestHandler):
    """Answers every POST with `respond(request_body)`, after `delay` seconds."""

    respond: ClassVar[Callable[[dict], tuple[int, dict]]] = staticmethod(lambda request: (500, {}))
    delay: ClassVar[float] = 0.0
    requests: ClassVar[list[dict]] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append(body)
        time.sleep(self.delay)
        status, answer = type(self).respond(body)
        payload = json.dumps(answer).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except BrokenPipeError:
            pass  # the client timed out first (test_a_slow_response_times_out_as_retryable)

    def log_message(self, *args):
        pass


Responder = Callable[[dict], tuple[int, dict]]


class ProviderContract(SimpleTestCase):
    """Run once per provider by each subclass, which says how its API speaks (deleted from the
    module below so the runner doesn't collect it on its own)."""

    server: ClassVar[ThreadingHTTPServer]
    provider: ClassVar[str]

    def answer_with_tool_call(self, request: dict, arguments: Any) -> dict:
        raise NotImplementedError

    def answer_with_text(self, request: dict, text: str) -> dict:
        raise NotImplementedError

    def error(self, status: int) -> dict:
        raise NotImplementedError

    def sent_prompt(self, request: dict) -> tuple[str, str]:
        """(instructions, user message) as the provider received them."""
        raise NotImplementedError

    def picker(self, timeout: float = 2) -> LLMPicker:
        return LLMPicker(build_model(f"{self.provider}:test-model", timeout))

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeProviderApi)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)

    def setUp(self):
        _FakeProviderApi.delay, _FakeProviderApi.requests = 0.0, []
        base_url = f"http://127.0.0.1:{self.server.server_port}"
        env = {"ANTHROPIC_BASE_URL": base_url, "OPENAI_BASE_URL": f"{base_url}/v1"}
        patcher = mock.patch.dict("os.environ", env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _respond(self, respond: Responder) -> None:
        _FakeProviderApi.respond = staticmethod(respond)  # type: ignore[assignment]

    def test_returns_the_validated_picks_and_sends_the_shortlist(self):
        answer = {"response": [{"recipe_id": 2, "description": "Light."}]}
        self._respond(lambda r: (200, self.answer_with_tool_call(r, answer)))

        picks = self.picker().pick("something light", SHORTLIST, count=1)

        self.assertEqual(picks, [Pick(recipe_id=2, description="Light.")])
        instructions, user_message = self.sent_prompt(_FakeProviderApi.requests[0])
        self.assertIn("Return exactly 1 picks", instructions)
        self.assertEqual(json.loads(user_message)["candidates"], SHORTLIST)

    def test_answers_that_fail_validation_are_unusable(self):
        bad_answers: list[Callable[[dict], dict]] = [
            lambda r: self.answer_with_text(r, "Here are some recipes!"),
            lambda r: self.answer_with_tool_call(r, {"response": [{"recipe_id": 1}]}),
            lambda r: self.answer_with_tool_call(r, {"response": [{"recipe_id": "one", "description": "x"}]}),
        ]
        for i, answer in enumerate(bad_answers):
            with self.subTest(answer=i):
                self._respond(lambda r, answer=answer: (200, answer(r)))  # type: ignore[misc]
                with self.assertRaises(UnusablePicks):
                    self.picker().pick("x", SHORTLIST, count=1)

    def test_a_bad_answer_is_not_retried_in_process(self):
        self._respond(lambda r: (200, self.answer_with_text(r, "no tool call")))

        with self.assertRaises(UnusablePicks):
            self.picker().pick("x", SHORTLIST, count=1)

        self.assertEqual(len(_FakeProviderApi.requests), 1)

    def test_requests_the_provider_will_never_accept_fail_permanently(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                self._respond(lambda r, status=status: (status, self.error(status)))  # type: ignore[misc]
                with self.assertRaises(PermanentFailure):
                    self.picker().pick("x", SHORTLIST, count=1)

    def test_rate_limits_overload_and_server_errors_stay_retryable_without_sdk_retries(self):
        for status in (408, 429, 500, 503, 529):
            with self.subTest(status=status):
                _FakeProviderApi.requests = []
                self._respond(lambda r, status=status: (status, self.error(status)))  # type: ignore[misc]
                with self.assertRaises(ModelAPIError) as caught:
                    self.picker().pick("x", SHORTLIST, count=1)
                self.assertNotIsInstance(caught.exception, PermanentFailure)
                self.assertEqual(len(_FakeProviderApi.requests), 1)

    def test_a_slow_response_times_out_as_retryable(self):
        _FakeProviderApi.delay = 0.5
        self._respond(lambda r: (200, self.answer_with_text(r, "late")))

        with self.assertRaises(ModelAPIError):
            self.picker(timeout=0.1).pick("x", SHORTLIST, count=1)


@override_settings(ANTHROPIC_API_KEY="test-key")
class AnthropicPickerTests(ProviderContract):
    provider = "anthropic"

    def _message(self, request: dict, content: list[dict], stop_reason: str) -> dict:
        return {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": request["model"],
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }

    def answer_with_tool_call(self, request, arguments):
        tool = {"type": "tool_use", "id": "toolu_1", "name": request["tools"][0]["name"], "input": arguments}
        return self._message(request, [tool], "tool_use")

    def answer_with_text(self, request, text):
        return self._message(request, [{"type": "text", "text": text}], "end_turn")

    def error(self, status):
        return {"type": "error", "error": {"type": "api_error", "message": "nope"}}

    def sent_prompt(self, request):
        system = request["system"]
        instructions = system if isinstance(system, str) else "".join(block["text"] for block in system)
        content = request["messages"][0]["content"]
        user = content if isinstance(content, str) else "".join(block["text"] for block in content)
        return instructions, user


@override_settings(OPENAI_API_KEY="test-key")
class OpenAIPickerTests(ProviderContract):
    provider = "openai"

    def _completion(self, request: dict, message: dict, finish_reason: str) -> dict:
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": request["model"],
            "choices": [{"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant"} | message}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }

    def answer_with_tool_call(self, request, arguments):
        call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": request["tools"][0]["function"]["name"], "arguments": json.dumps(arguments)},
        }
        return self._completion(request, {"content": None, "tool_calls": [call]}, "tool_calls")

    def answer_with_text(self, request, text):
        return self._completion(request, {"content": text}, "stop")

    def error(self, status):
        return {"error": {"message": "nope", "type": "api_error", "code": None}}

    def sent_prompt(self, request):
        by_role = {message["role"]: message["content"] for message in request["messages"]}
        return by_role.get("system") or by_role["developer"], by_role["user"]


del ProviderContract


class ModelProviderTests(SimpleTestCase):
    @override_settings(ANTHROPIC_API_KEY="k", OPENAI_API_KEY="k", AI_SEARCH_MODEL_TIMEOUT_SECONDS=12.5)
    def test_every_provider_has_a_timeout_and_no_sdk_retries(self):
        for provider in ("anthropic", "openai"):
            with self.subTest(provider=provider), override_settings(AI_SEARCH_MODEL=f"{provider}:m"):
                model = LLMPicker().model
                assert isinstance(model, AnthropicModel | OpenAIChatModel)
                client = model.client
                self.assertEqual(client.max_retries, 0)
                self.assertEqual(client.timeout, 12.5)

    @override_settings(AI_SEARCH_MODEL="openai:gpt-test", OPENAI_API_KEY="k", AI_SEARCH_MODEL_TIMEOUT_SECONDS=7.0)
    def test_the_default_model_comes_from_settings(self):
        model = LLMPicker().model

        self.assertEqual((model.system, model.model_name), ("openai", "gpt-test"))

    def test_malformed_specs_and_unknown_providers_are_configuration_errors(self):
        for spec in ("claude-haiku", "anthropic:", "gemini:flash"):
            with self.subTest(spec=spec), self.assertRaises(ImproperlyConfigured):
                ModelSpec.parse(spec)

    @override_settings(ANTHROPIC_API_KEY="")
    def test_a_missing_api_key_is_a_configuration_error(self):
        with self.assertRaises(ImproperlyConfigured):
            build_model("anthropic:m", 30)
