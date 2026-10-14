"""LLM adapters for AI search resolution, through Pydantic AI (see queries/services/resolution.py):
`LLMInterpreter` (a `RequestInterpreter`) and `LLMPicker` (a `RecipePicker`).

The provider and model come from AI_SEARCH_MODEL (queries/services/model_providers.py),
so switching from Claude to another provider is configuration, not code.
Pydantic AI asks the model for its answer through a structured output tool and
validates it against the output type, replacing hand-parsed JSON.

Retries belong to the Celery task, so these adapters never retry: the SDK's
retries are off, and so are Pydantic AI's output retries (a bad answer is
re-sampled by the task's next attempt, inside the same backoff budget).
Provider errors are classified at this seam (`_run`): requests the provider will
never accept (auth, permissions, malformed) become `PermanentFailure`; an answer
that fails validation becomes `UnusableAnswer` (`UnusablePicks` for the picker);
everything else (rate limits, overload, 5xx, timeouts, connection errors)
propagates as Pydantic AI's `ModelAPIError` and is retried.
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
from queries.services.resolution import Interpretation, PermanentFailure, Pick, UnusableAnswer, UnusablePicks

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
        "Each candidate's goal_checks say, per nutrition target, the per-meal target, the "
        "recipe's value and whether it is met: prefer candidates that meet more targets, and "
        "say in the description how the recipe compares to them. "
        f"Use each candidate's recipe_id exactly as given. Return exactly {count} picks."
    )


_interpreter = Agent(
    output_type=Interpretation,
    retries=0,
    instructions=(
        "You turn a request for something to eat into a recipe search. Return search_phrase: the "
        "dish, ingredients, cuisine or meal the user describes, as a short phrase. Return intents: "
        "only nutrients (calories, protein, carbs, fat, fiber) the user explicitly wants high "
        "(at_least) or low (at_most), e.g. 'high fiber', 'low carb', 'light' (calories at_most). "
        "Set amount only when the user states one for this meal (e.g. 'at least 30 g protein' -> 30); "
        "calories in kcal, the rest in grams. No nutrient mentioned means no intents. "
        "Set on_topic false only when the request is clearly not about food, meals, recipes or "
        "nutrition (e.g. 'write me a poem'); vague or emotional food requests are on topic; when unsure, true."
    ),
    model_settings={"max_tokens": 512},
)


def _run(agent: Agent[Any, Any], model: Model, user_prompt: str, deps: Any = None) -> Any:
    """One agent run, its failures classified for the task's retry policy (module docstring)."""
    try:
        return agent.run_sync(user_prompt, model=model, deps=deps)
    except ModelHTTPError as exc:
        if exc.status_code < 500 and exc.status_code not in _RETRYABLE_CLIENT_ERRORS:
            raise PermanentFailure(f"{model.system} rejected the request: HTTP {exc.status_code}") from exc
        raise


def _log_usage(event: str, model: Model, started: float, result: Any) -> None:
    usage = result.usage
    logger.info(
        event,
        extra={
            "provider": model.system,
            "model": model.model_name,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            # Quote this when asking the provider's support about a specific call.
            "provider_response_id": result.response.provider_response_id,
        },
    )


def _default_model() -> Model:
    return build_model(settings.AI_SEARCH_MODEL, settings.AI_SEARCH_MODEL_TIMEOUT_SECONDS)


class LLMInterpreter:
    def __init__(self, model: Model | None = None) -> None:
        self._model = model or _default_model()

    def interpret(self, prompt: str) -> Interpretation:
        started = time.monotonic()
        try:
            result = _run(_interpreter, self._model, prompt)
        except UnexpectedModelBehavior as exc:
            logger.warning("ai_interpretation_unusable", extra={"model": self._model.model_name, "error": exc.message})
            raise UnusableAnswer(f"unusable interpretation: {exc.message}") from exc
        _log_usage("ai_interpretation_completed", self._model, started, result)
        return result.output


class LLMPicker:
    def __init__(self, model: Model | None = None) -> None:
        self._model = model or _default_model()

    @property
    def model(self) -> Model:
        return self._model

    def pick(self, prompt: str, shortlist: list[dict[str, Any]], count: int) -> list[Pick]:
        started = time.monotonic()
        user_prompt = json.dumps({"user_request": prompt, "candidates": shortlist})
        try:
            result = _run(_agent, self._model, user_prompt, deps=count)
        except UnexpectedModelBehavior as exc:
            logger.warning(
                "ai_selection_unusable",
                extra={"model": self._model.model_name, "error": exc.message, "response_preview": str(exc.body)[:500]},
            )
            raise UnusablePicks(f"unusable picks: {exc.message}") from exc

        _log_usage("ai_selection_completed", self._model, started, result)
        return [Pick(recipe_id=p.recipe_id, description=p.description) for p in result.output]
