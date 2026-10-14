"""AI search resolution: a prompt (and the user's goals) in, described recipes out.

The deep module behind `POST /api/queries`. A fixed flow, each step reported
as it starts (`Step`), so the page can show progress:

1. understand: an interpreter turns the prompt into a search phrase and the
   nutrients it asks for, merged with the user's goals into nutrition targets;
2. search: recipes meeting every target, by similarity to the phrase, widened
   in the fixed order of `targets.widening_levels` while too few match;
3. check: each shortlisted recipe against each target (skipped with no targets);
4. choose: a picker chooses and describes the final few.

The order is code, not the model's choice: only steps 1 and 4 call an LLM
(`AI_CALLS_PER_ATTEMPT`). The collaborators that are slow, paid or heavy sit
behind seams, each with two adapters:

- `RequestInterpreter`: `queries.services.generation.LLMInterpreter` in production,
  `queries.tests.fakes.FakeInterpreter` in tests.
- `QueryEmbedder`: `recipes.services.embeddings.LocalEmbedder` in production,
  `queries.tests.fakes.FakeEmbedder` in tests.
- `RecipePicker`: `queries.services.generation.LLMPicker` (any LLM provider, via Pydantic AI) in production,
  `queries.tests.fakes.FakePicker` in tests.

Settings choose the adapters (`AI_SEARCH_INTERPRETER`, `AI_SEARCH_EMBEDDER`, `AI_SEARCH_PICKER`);
`default_resolver()` builds them once per process. Retrying is not this
module's job: it raises, and says through the exception type whether a retry
can help (`PermanentFailure`), and the Celery task (queries/tasks.py) decides.
"""

import functools
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Protocol

from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.module_loading import import_string
from pydantic import BaseModel, Field

from accounts.models import Profile
from queries.services import retrieval
from queries.services.targets import (
    GOAL_FIELD,
    GoalCheck,
    Nutrient,
    NutrientIntent,
    NutritionTarget,
    check,
    merge_targets,
    rank_key,
    widening_levels,
)
from recipes.models import Recipe

logger = logging.getLogger(__name__)


# The interpreter and the picker; the task's worst-case budget multiplies by this.
AI_CALLS_PER_ATTEMPT = 2


class Step(StrEnum):
    """A stage of resolving a request, in order. Only the codes cross the API; the page owns the labels."""

    UNDERSTANDING = "understanding"
    SEARCHING = "searching"
    WIDENING = "widening"
    CHECKING = "checking"
    CHOOSING = "choosing"


StepReporter = Callable[[Step], object]  # any return value is ignored


class Interpretation(BaseModel, frozen=True):
    search_phrase: str = Field(min_length=1, max_length=300, description="What to search the recipes for")
    intents: list[NutrientIntent] = Field(default_factory=list, description="Nutrients the user asks to be high or low")


@dataclass(frozen=True)
class Resolution:
    results: list[dict[str, Any]]  # the shape stored in `QueryRequest.results`
    unmet_targets: list[str]  # nutrients none of the results meets


@dataclass(frozen=True)
class Pick:
    recipe_id: int
    description: str


class RequestInterpreter(Protocol):
    def interpret(self, prompt: str) -> Interpretation: ...


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


class RecipePicker(Protocol):
    def pick(self, prompt: str, shortlist: list[dict[str, Any]], count: int) -> list[Pick]:
        """Choose `count` recipes from `shortlist` (dicts with `recipe_id` and nutrition) and say why each fits."""
        ...


class PermanentFailure(Exception):
    """Retrying would fail the same way: bad credentials, or a request the provider rejects as invalid."""


class UnusableAnswer(Exception):
    """A model answered, but not usably (unparseable or invalid). A new sample often fixes this, so it is retryable."""


class UnusablePicks(UnusableAnswer):
    """The picker's answer: unparseable, too few, or ids outside the shortlist."""


def _ignore_step(step: Step) -> None:
    pass


@dataclass(frozen=True)
class Resolver:
    interpreter: RequestInterpreter
    embedder: QueryEmbedder
    picker: RecipePicker
    candidate_count: int
    shortlist_size: int
    result_count: int

    def resolve(self, prompt: str, profile: Profile | None, report: StepReporter = _ignore_step) -> Resolution:
        report(Step.UNDERSTANDING)
        interpretation = self.interpreter.interpret(prompt)
        targets = merge_targets(_daily_goals(profile), interpretation.intents)
        query_embedding = self.embedder.embed_query(interpretation.search_phrase)

        report(Step.SEARCHING)
        shortlist = self._search(query_embedding, targets, report)

        checks: dict[int, tuple[GoalCheck, ...]] = {}
        if targets:
            report(Step.CHECKING)
            checks = {recipe.id: check(retrieval.nutrient_values(recipe), targets) for recipe in shortlist}

        report(Step.CHOOSING)
        results = self._pick(prompt, shortlist, checks)
        met = {c["nutrient"] for result in results for c in result["goal_checks"] if c["met"]}
        return Resolution(results, [str(t.nutrient) for t in targets if t.nutrient not in met])

    def _search(
        self, query_embedding: list[float], targets: tuple[NutritionTarget, ...], report: StepReporter
    ) -> list[Recipe]:
        """Every level's recipes are pooled, so widening adds candidates and never loses better ones."""
        pool: dict[int, Recipe] = {}
        widened = False
        for level in widening_levels(targets):
            if len(pool) >= self.shortlist_size:
                break
            if level.widened and not widened:
                report(Step.WIDENING)  # once, however many widening levels run
                widened = True
            for recipe in retrieval.search_level(query_embedding, level, self.candidate_count):
                pool.setdefault(recipe.id, recipe)
        ranked = sorted(pool.values(), key=lambda recipe: rank_key(retrieval.nutrient_values(recipe), targets))
        return ranked[: self.shortlist_size]

    def _pick(
        self, prompt: str, shortlist: list[Recipe], checks: dict[int, tuple[GoalCheck, ...]]
    ) -> list[dict[str, Any]]:
        by_id = {recipe.id: recipe for recipe in shortlist}
        candidates = [_candidate(recipe, checks.get(recipe.id, ())) for recipe in shortlist]
        picks = self.picker.pick(prompt, candidates, self.result_count)

        results: list[dict[str, Any]] = []
        chosen: set[int] = set()
        for pick in picks:
            recipe = by_id.get(pick.recipe_id)
            if recipe is None or pick.recipe_id in chosen:
                logger.warning("pick_discarded", extra={"recipe_id": pick.recipe_id, "known": recipe is not None})
                continue
            chosen.add(pick.recipe_id)
            results.append(_result(recipe, pick.description, checks.get(recipe.id, ())))
            if len(results) == self.result_count:
                return results
        raise UnusablePicks(f"expected {self.result_count} distinct picks from the shortlist, got {len(results)}")


@functools.cache
def default_resolver() -> Resolver:
    """The process-wide resolver, with the adapters named in settings (validated at startup by QueriesConfig)."""
    return Resolver(
        interpreter=import_string(settings.AI_SEARCH_INTERPRETER)(),
        embedder=import_string(settings.AI_SEARCH_EMBEDDER)(),
        picker=import_string(settings.AI_SEARCH_PICKER)(),
        candidate_count=settings.RETRIEVAL_CANDIDATE_COUNT,
        shortlist_size=settings.RETRIEVAL_RERANKED_COUNT,
        result_count=settings.RESULT_COUNT,
    )


_RESOLVER_SETTINGS = {
    "AI_SEARCH_INTERPRETER",
    "AI_SEARCH_EMBEDDER",
    "AI_SEARCH_PICKER",
    "RETRIEVAL_CANDIDATE_COUNT",
    "RETRIEVAL_RERANKED_COUNT",
    "RESULT_COUNT",
}


@receiver(setting_changed)
def _rebuild_resolver(setting: str, **kwargs: Any) -> None:
    # override_settings in tests swaps adapters; the next call must build with them.
    if setting in _RESOLVER_SETTINGS:
        default_resolver.cache_clear()


def _daily_goals(profile: Profile | None) -> dict[Nutrient, float | None]:
    if profile is None:
        return {}
    return {nutrient: getattr(profile, field) for nutrient, field in GOAL_FIELD.items()}


def _goal_checks(checks: tuple[GoalCheck, ...]) -> list[dict[str, Any]]:
    return [asdict(c) | {"target": round(c.target, 1)} for c in checks]


def _candidate(recipe: Recipe, checks: tuple[GoalCheck, ...]) -> dict[str, Any]:
    """What the picker sees about a shortlisted recipe, including how it meets the targets."""
    return {
        "recipe_id": recipe.id,
        "recipe_name": recipe.recipe_name,
        "calories_per_serving": recipe.calories_per_serving,
        "protein_g_per_serving": recipe.protein_g_per_serving,
        "carbs_g_per_serving": recipe.carbs_g_per_serving,
        "fat_g_per_serving": recipe.fat_g_per_serving,
        "fiber_g_per_serving": recipe.fiber_g_per_serving,
        "sugar_g_per_serving": recipe.sugar_g_per_serving,
        "sodium_mg_per_serving": recipe.sodium_mg_per_serving,
        "diet_labels": recipe.diet_labels,
        "health_labels": recipe.health_labels,
        "goal_checks": _goal_checks(checks),
    }


def _result(recipe: Recipe, description: str, checks: tuple[GoalCheck, ...]) -> dict[str, Any]:
    """One entry of `QueryRequest.results` (served as `ResultOut`, queries/api.py)."""
    return {
        "recipe_id": recipe.id,
        "recipe_name": recipe.recipe_name,
        "description": description,
        "source_url": recipe.source_url,
        "image_url": recipe.image_url,
        "calories_per_serving": recipe.calories_per_serving,
        "protein_g_per_serving": recipe.protein_g_per_serving,
        "carbs_g_per_serving": recipe.carbs_g_per_serving,
        "fat_g_per_serving": recipe.fat_g_per_serving,
        "fiber_g_per_serving": recipe.fiber_g_per_serving,
        "sugar_g_per_serving": recipe.sugar_g_per_serving,
        "sodium_mg_per_serving": recipe.sodium_mg_per_serving,
        "goal_checks": _goal_checks(checks),
    }
