"""AI search resolution: a prompt (and the user's goals) in, described recipes out.

The deep module behind `POST /api/queries`. It embeds the prompt, shortlists
recipes by vector similarity (re-ranked by goals when the user has any), and
has a picker choose and describe the final few. The two collaborators that
are slow, paid or heavy sit behind seams, each with two adapters:

- `QueryEmbedder`: `recipes.services.embeddings.LocalEmbedder` in production,
  `queries.tests.fakes.FakeEmbedder` in tests.
- `RecipePicker`: `queries.services.generation.ClaudePicker` in production,
  `queries.tests.fakes.FakePicker` in tests.

Settings choose the adapters (`AI_SEARCH_EMBEDDER`, `AI_SEARCH_PICKER`);
`default_resolver()` builds them once per process. Retrying is not this
module's job: it raises, and says through the exception type whether a retry
can help (`PermanentFailure`), and the Celery task (queries/tasks.py) decides.
"""

import functools
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.module_loading import import_string

from accounts.models import Profile
from queries.services import retrieval
from recipes.models import Recipe

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Pick:
    recipe_id: int
    description: str


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


class RecipePicker(Protocol):
    def pick(self, prompt: str, shortlist: list[dict[str, Any]], count: int) -> list[Pick]:
        """Choose `count` recipes from `shortlist` (dicts with `recipe_id` and nutrition) and say why each fits."""
        ...


class PermanentFailure(Exception):
    """Retrying would fail the same way: bad credentials, or a request the provider rejects as invalid."""


class UnusablePicks(Exception):
    """The picker answered, but not usably (unparseable, too few, ids outside the shortlist).
    A new sample often fixes this, so it is retryable."""


@dataclass(frozen=True)
class Resolver:
    embedder: QueryEmbedder
    picker: RecipePicker
    candidate_count: int
    shortlist_size: int
    result_count: int

    def resolve(self, prompt: str, profile: Profile | None) -> list[dict[str, Any]]:
        """Returns `result_count` result dicts (the shape stored in `QueryRequest.results`)."""
        shortlist = retrieval.select_candidates(
            query_embedding=self.embedder.embed_query(prompt),
            profile=profile,
            candidate_count=self.candidate_count,
            reranked_count=self.shortlist_size,
        )
        by_id = {recipe.id: recipe for recipe in shortlist}
        picks = self.picker.pick(prompt, [_candidate(recipe) for recipe in shortlist], self.result_count)

        results: list[dict[str, Any]] = []
        chosen: set[int] = set()
        for pick in picks:
            recipe = by_id.get(pick.recipe_id)
            if recipe is None or pick.recipe_id in chosen:
                logger.warning("pick_discarded", extra={"recipe_id": pick.recipe_id, "known": recipe is not None})
                continue
            chosen.add(pick.recipe_id)
            results.append(_result(recipe, pick.description))
            if len(results) == self.result_count:
                return results
        raise UnusablePicks(f"expected {self.result_count} distinct picks from the shortlist, got {len(results)}")


@functools.cache
def default_resolver() -> Resolver:
    """The process-wide resolver, with the adapters named in settings (validated at startup by QueriesConfig)."""
    return Resolver(
        embedder=import_string(settings.AI_SEARCH_EMBEDDER)(),
        picker=import_string(settings.AI_SEARCH_PICKER)(),
        candidate_count=settings.RETRIEVAL_CANDIDATE_COUNT,
        shortlist_size=settings.RETRIEVAL_RERANKED_COUNT,
        result_count=settings.RESULT_COUNT,
    )


_RESOLVER_SETTINGS = {
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


def _candidate(recipe: Recipe) -> dict[str, Any]:
    """What the picker sees about a shortlisted recipe."""
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
    }


def _result(recipe: Recipe, description: str) -> dict[str, Any]:
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
    }
