"""Builds the Pydantic AI `Model` that AI search talks to, from a "provider:model" string.

`AI_SEARCH_MODEL` names it (e.g. "anthropic:claude-haiku-4-5-20251001",
"openai:gpt-4.1-mini"). Every provider is built the same way: one request is
bounded by AI_SEARCH_MODEL_TIMEOUT_SECONDS and the SDK's own retries are off,
because the Celery task owns retrying (docs/adr/0005). Pydantic AI's
`infer_model` would build the same models but with SDK retries on, which
multiplies with the task's retries and blows the frontend's wait budget.

Adding a provider is one builder in `_BUILDERS` (plus its `pydantic-ai-slim`
extra and API key setting). The "openai" provider also covers any
OpenAI-compatible endpoint (OpenRouter, Ollama, vLLM...) through OPENAI_BASE_URL.
"""

from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from pydantic_ai.models import Model


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model_name: str

    @classmethod
    def parse(cls, spec: str) -> "ModelSpec":
        """Raises ImproperlyConfigured for a malformed spec or a provider with no builder."""
        provider, sep, model_name = spec.partition(":")
        if not sep or not model_name:
            raise ImproperlyConfigured(f'AI_SEARCH_MODEL must look like "provider:model", got {spec!r}')
        if provider not in _BUILDERS:
            raise ImproperlyConfigured(
                f"AI_SEARCH_MODEL: unsupported provider {provider!r} (supported: {', '.join(sorted(_BUILDERS))})"
            )
        return cls(provider, model_name)


def build_model(spec: str, timeout: float) -> Model:
    parsed = ModelSpec.parse(spec)
    return _BUILDERS[parsed.provider](parsed.model_name, timeout)


def _anthropic(model_name: str, timeout: float) -> Model:
    from anthropic import AsyncAnthropic
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    # base_url comes from ANTHROPIC_BASE_URL when set (the E2E stack points it at a stub).
    client = AsyncAnthropic(api_key=_api_key("ANTHROPIC_API_KEY"), timeout=timeout, max_retries=0)
    return AnthropicModel(model_name, provider=AnthropicProvider(anthropic_client=client))


def _openai(model_name: str, timeout: float) -> Model:
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    # base_url comes from OPENAI_BASE_URL when set, for OpenAI-compatible endpoints.
    client = AsyncOpenAI(api_key=_api_key("OPENAI_API_KEY"), timeout=timeout, max_retries=0)
    return OpenAIChatModel(model_name, provider=OpenAIProvider(openai_client=client))


def _api_key(name: str) -> str:
    # Checked when the model is built (first AI search in a worker), not at startup: the web
    # process and management commands never call the model and shouldn't need the key.
    key = getattr(settings, name)
    if not key:
        raise ImproperlyConfigured(f"{name} is not set, but AI_SEARCH_MODEL uses its provider")
    return key


_BUILDERS: dict[str, Callable[[str, float], Model]] = {
    "anthropic": _anthropic,
    "openai": _openai,
}
