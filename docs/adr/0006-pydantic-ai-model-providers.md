# 0006 — Pydantic AI for the picker, with the model provider chosen in configuration

Date: 2026-10-08 · Status: accepted · Amends 0005 (the picker adapter and its timeout setting)

## Context

The picker (`RecipePicker`, ADR 0005) was `ClaudePicker`: Anthropic SDK calls, a prompt asking for bare JSON, and a hand-written parser for it (code fences, wrong types, missing keys). Using another provider would have meant a second adapter with its own client, prompt format, parser and error mapping. We want to be able to add providers (OpenAI, Gemini, OpenAI-compatible hosts, local models) without rewriting the picker each time.

## Decision

- **One picker for every provider: `LLMPicker`** (`queries/services/generation.py`), built on Pydantic AI.
  - It asks the model for `list[_PickOut]` through Pydantic AI's structured-output tool.
  - Pydantic validates the answer, which replaces the hand-written JSON parser.
- **The provider is configuration.** `AI_SEARCH_MODEL="provider:model"` sets it; the default is `anthropic:claude-haiku-4-5-20251001`.
  - `queries/services/model_providers.py` builds the Pydantic AI `Model` from that string, through a small registry of builders: `anthropic`, plus `openai`, which also covers any OpenAI-compatible endpoint through `OPENAI_BASE_URL`.
  - Adding a provider means adding a builder, its `pydantic-ai-slim` extra and its API key setting. `QueriesConfig.ready` rejects a malformed spec or an unknown provider at startup.
- **We build the provider clients ourselves**, rather than using Pydantic AI's `infer_model`. That lets every client have:
  - a timeout (`AI_SEARCH_MODEL_TIMEOUT_SECONDS`, default 30, replacing `CLAUDE_TIMEOUT_SECONDS`);
  - `max_retries=0`.

  ADR 0005's single retry layer (the Celery task) therefore still holds for every provider.
- **Pydantic AI's own retries are off too** (`Agent(retries=0)`). When an answer fails validation, Pydantic AI raises `UnexpectedModelBehavior`. The picker turns that into `UnusablePicks`, and the task's next attempt samples again. Retrying inside the call as well would double the worst-case time per attempt, and the frontend's 150 s budget assumes it doesn't.
- **Errors are classified once, provider-independently**, using Pydantic AI's normalised exceptions:
  - `ModelHTTPError` with a 4xx other than 408, 409 or 429 becomes `PermanentFailure`;
  - other `ModelAPIError`s (429, 5xx, 529, timeouts, connection errors) are retried.
- **A missing API key for the configured provider** raises `ImproperlyConfigured` when the worker first builds the model. The task treats it like a permanent failure. The check isn't done at startup, because the web process and management commands never call the model.

## Consequences

- **Each new provider runs the same tests.** `queries/tests/test_llm_picker.py` runs one contract against a fake HTTP server per provider, through the real SDK. A new provider gets a subclass that says how its API's tool calls and errors look.
- **Output arrives as a tool call** instead of text, so the E2E Claude stub (`frontend/e2e/claude-stub`) now answers with a `tool_use` block for the tool named in the request.
- **Log events are now provider-neutral.**
  - `claude_selection_completed` becomes `ai_selection_completed`, which adds `provider` and `provider_response_id` and drops `stop_reason`.
  - `claude_selection_unparseable` becomes `ai_selection_unusable`.
- **New dependency:** `pydantic-ai-slim[anthropic,openai]`, which is maintained by the Pydantic team. Only the SDKs for the registered providers are installed.
- **Pydantic AI drives async clients from synchronous code** (`run_sync`, on the worker thread's event loop). That is fine for the prefork Celery worker. An async worker would call `run` instead.
- **Not done:**
  - a fallback model when the primary provider is down (Pydantic AI's `FallbackModel` would fit behind `build_model`);
  - per-provider prompt tuning;
  - a circuit breaker (still open from 0005).
