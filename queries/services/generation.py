"""`RecipePicker` adapter for any LLM provider, through Pydantic AI (see queries/services/resolution.py).

The provider and model come from AI_SEARCH_MODEL (queries/services/model_providers.py),
so switching from Claude to another provider is configuration, not code.
Pydantic AI asks the model for its answer through a structured output tool and
validates it against `_PickOut`, replacing hand-parsed JSON.

Retries belong to the Celery task, so this adapter never retries: the SDK's
retries are off, and so are Pydantic AI's output retries (a bad answer is
re-sampled by the task's next attempt, inside the same backoff budget).
Provider errors are classified at this seam: requests the provider will never
accept (auth, permissions, malformed) become `PermanentFailure`; an answer
that fails validation becomes `UnusablePicks`; everything else (rate limits,
overload, 5xx, timeouts, connection errors) propagates as Pydantic AI's
`ModelAPIError` and is retried.
"""

import json
import logging
import time
from typing import Any

import pydantic_ai
from django.conf import settings
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.models import Model

from queries.services.model_providers import build_model
from queries.services.resolution import PermanentFailure, Pick, UnusablePicks

logger = logging.getLogger(__name__)

# The worker's output is structured logs; keep Pydantic AI's first-run terminal banner out of them.
pydantic_ai.BANNER_ENABLED = False

# Below 500, only these mean "try again later"; any other 4xx will fail the same way every time.
_RETRYABLE_CLIENT_ERRORS = {408, 409, 429}


class _PickOut(BaseModel):
    recipe_id: int
    description: str


_agent = Agent(
    output_type=list[_PickOut],
    deps_type=int,
    retries=0,
    # Keep the response to what the output tool needs; a pick is one or two sentences.
    model_settings={"max_tokens": 1024},
)


@_agent.instructions
def _instructions(ctx: RunContext[int]) -> str:
    count = ctx.deps
    return (
        "You are a nutrition assistant. Given a user's request and a shortlist of "
        "candidate recipes with their per-serving nutrition data, select the "
        f"{count} recipes that best match the request and write a short "
        "(1-2 sentence) description for each explaining why it fits. "
        f"Use each candidate's recipe_id exactly as given. Return exactly {count} picks."
    )


class LLMPicker:
    def __init__(self, model: Model | None = None) -> None:
        self._model = model or build_model(settings.AI_SEARCH_MODEL, settings.AI_SEARCH_MODEL_TIMEOUT_SECONDS)

    @property
    def model(self) -> Model:
        return self._model

    def pick(self, prompt: str, shortlist: list[dict[str, Any]], count: int) -> list[Pick]:
        started = time.monotonic()
        user_prompt = json.dumps({"user_request": prompt, "candidates": shortlist})
        try:
            result = _agent.run_sync(user_prompt, model=self._model, deps=count)
        except ModelHTTPError as exc:
            if exc.status_code < 500 and exc.status_code not in _RETRYABLE_CLIENT_ERRORS:
                raise PermanentFailure(f"{self._model.system} rejected the request: HTTP {exc.status_code}") from exc
            raise
        except UnexpectedModelBehavior as exc:
            logger.warning(
                "ai_selection_unusable",
                extra={"model": self._model.model_name, "error": exc.message, "response_preview": str(exc.body)[:500]},
            )
            raise UnusablePicks(f"unusable picks: {exc.message}") from exc

        usage = result.usage
        logger.info(
            "ai_selection_completed",
            extra={
                "provider": self._model.system,
                "model": self._model.model_name,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                # Quote this when asking the provider's support about a specific call.
                "provider_response_id": result.response.provider_response_id,
            },
        )
        return [Pick(recipe_id=p.recipe_id, description=p.description) for p in result.output]
