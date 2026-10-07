import logging
import time
from typing import Annotated

from django.conf import settings
from ninja import Field, Query, Router, Schema
from ninja.security import django_auth

from recipes.services.keyword_search import search_recipes, search_terms

logger = logging.getLogger(__name__)

router = Router(tags=["keyword-search"], auth=django_auth)


class RecipeOut(Schema):
    id: int
    recipe_name: str
    source_url: str
    image_url: str | None
    calories_per_serving: float | None
    protein_g_per_serving: float | None
    carbs_g_per_serving: float | None
    fat_g_per_serving: float | None
    fiber_g_per_serving: float | None
    sugar_g_per_serving: float | None
    sodium_mg_per_serving: float | None


class SearchParams(Schema):
    q: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]


class SearchOut(Schema):
    query: str
    results: list[RecipeOut]
    elapsed_ms: float


@router.get("", response=SearchOut)
def keyword_search(request, params: Query[SearchParams]):
    """Search without AI: synchronous, at most KEYWORD_SEARCH_RESULT_COUNT recipes.
    `elapsed_ms` is database search time, measured here."""
    query = params.q.strip()
    started = time.perf_counter()
    recipes = search_recipes(query, limit=settings.KEYWORD_SEARCH_RESULT_COUNT)
    elapsed_ms = (time.perf_counter() - started) * 1000

    logger.info(
        "keyword_search_completed",
        extra={"terms": len(search_terms(query)), "results": len(recipes), "duration_ms": round(elapsed_ms, 1)},
    )
    return SearchOut(
        query=query,
        results=[RecipeOut.from_orm(recipe) for recipe in recipes],
        elapsed_ms=elapsed_ms,
    )
