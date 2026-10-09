# 0005 — AI search resolution: injected adapters, Celery-native retries, failure classes

Date: 2026-10-08 · Status: accepted · Amended by 0006 (`ClaudePicker` became the provider-neutral `LLMPicker`; `CLAUDE_TIMEOUT_SECONDS` became `AI_SEARCH_MODEL_TIMEOUT_SECONDS`)

## Context

`queries/tasks.py` mixed four jobs: the Celery task, a retry loop that slept inside the worker (2 + 4 + 8 s), the embed → retrieve → pick steps, and the result serializers. Tests could reach the embedding model and Claude only by patching import paths.

The retry policy had two problems:
- Every exception was retried, so a revoked API key cost four calls and about 14 s before the user saw an error.
- The Anthropic client had the SDK's default 10-minute timeout and its own 2 retries, nested inside our 4 attempts: up to 12 calls per request.

## Decision

- **One AI search resolution module.** `queries/services/resolution.py` exposes `Resolver.resolve(prompt, profile)`, which returns the stored result dicts. Its collaborators sit behind two seams:
  - `QueryEmbedder`, with adapters `LocalEmbedder` and `FakeEmbedder`;
  - `RecipePicker`, with adapters `ClaudePicker` and `FakePicker`.
- **Settings choose the adapters** (`AI_SEARCH_EMBEDDER`, `AI_SEARCH_PICKER`), and `QueriesConfig.ready` checks them at startup. Tests switch to `queries/tests/fakes.py` with `override_settings`; nothing is patched by import path. `default_resolver()` builds the resolver once per process and rebuilds it when those settings change.
- **Failures are classified where they happen.** The resolver doesn't retry; the exception type tells the task whether a retry can help.
  - `ClaudePicker` raises `PermanentFailure` when Claude rejects the request: any 4xx except 408, 409 and 429.
  - Rate limits, overload (529), 5xx, timeouts and connection errors propagate unchanged and are retried.
  - Unusable model output raises `UnusablePicks` (unparseable JSON, ids outside the shortlist, too few picks). It is retried, because a new sample usually fixes it.
- **One retry layer, owned by Celery.** `resolve_query` re-queues itself up to `QUERY_TASK_MAX_RETRIES` (3) times, with exponential backoff and jitter: within [½, 1] × 2 s·2ⁿ. The worker is free while it waits, and a pending retry survives a worker restart.
  - The SDK's retries are off, and each Claude call is limited to `CLAUDE_TIMEOUT_SECONDS` (30 s).
  - The frontend waits up to 150 s, which covers the worst case of four 30 s timeouts plus backoff.
- **Duplicate and late deliveries are safe.** The task skips a request that is already done or errored, or that no longer exists.

## Consequences

- **Eager mode needs exception propagation off.** Celery eager mode re-raises `Retry` when `CELERY_TASK_EAGER_PROPAGATES` is on, instead of running the retry, so the setting is now off. The task records its own failures, and Celery still logs unexpected task crashes.
- **Each attempt is its own task run.** Logs carry `attempt` and per-attempt `duration_ms`; the whole wait is `QueryRequest.elapsed_seconds`.
- **A request still in progress when its message is delivered twice can resolve twice** (two Claude calls). The last write wins, and both results are valid. Locking the row while it runs would remove this, if it ever matters.
- **Not done:** a circuit breaker for Claude (failing fast while it's down across many requests), and a fallback such as returning the shortlist without descriptions.
