import time

from celery import shared_task
from django.conf import settings

from accounts.models import Profile
from queries.models import QueryRequest
from queries.services import generation, retrieval
from recipes.models import Recipe

RETRY_BACKOFF_SECONDS = 2


def _serialize_candidate(recipe: Recipe) -> dict:
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


def _serialize_result(recipe: Recipe, description: str) -> dict:
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


def _resolve_once(query_request: QueryRequest) -> list[dict]:
    profile = Profile.objects.filter(user_id=query_request.user_id).first()

    candidates = retrieval.select_candidates(
        prompt=query_request.prompt,
        profile=profile,
        candidate_count=settings.RETRIEVAL_CANDIDATE_COUNT,
        reranked_count=settings.RETRIEVAL_RERANKED_COUNT,
    )
    candidates_by_id = {recipe.id: recipe for recipe in candidates}

    selections = generation.select_and_describe(
        query_request.prompt,
        [_serialize_candidate(recipe) for recipe in candidates],
    )

    results = []
    for selection in selections[: settings.RESULT_COUNT]:
        recipe = candidates_by_id.get(selection["recipe_id"])
        if recipe is None:
            continue
        results.append(_serialize_result(recipe, selection["description"]))

    if len(results) != settings.RESULT_COUNT:
        raise ValueError(
            f"Expected {settings.RESULT_COUNT} results, got {len(results)} "
            "(model likely referenced a recipe_id outside the candidate list)"
        )
    return results


@shared_task
def resolve_query(query_request_id: int):
    """Embed the prompt, retrieve/rerank candidates, and have Claude pick and
    describe the final results. Transient failures (OpenAI/Claude API
    errors) are retried a few times with backoff before the request is
    marked as errored.

    Celery's own `Task.retry()` requires a real broker + worker loop to
    actually requeue the task; under `CELERY_TASK_ALWAYS_EAGER` (as used in
    tests, and generally not a fit for this synchronous-lookup retry) it
    just raises once. So retries are handled with a plain loop instead.
    """
    query_request = QueryRequest.objects.get(id=query_request_id)
    query_request.status = QueryRequest.Status.RUNNING
    query_request.save(update_fields=["status", "updated_at"])

    last_exc: Exception | None = None
    for attempt in range(settings.QUERY_TASK_MAX_RETRIES + 1):
        try:
            results = _resolve_once(query_request)
        except Exception as exc:  # noqa: BLE001 - any failure here should retry, then error out
            last_exc = exc
            if attempt < settings.QUERY_TASK_MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
            continue
        else:
            query_request.results = results
            query_request.status = QueryRequest.Status.DONE
            query_request.save(update_fields=["results", "status", "updated_at"])
            return

    query_request.status = QueryRequest.Status.ERROR
    query_request.error_message = str(last_exc)
    query_request.save(update_fields=["status", "error_message", "updated_at"])
