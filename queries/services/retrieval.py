"""Turning an embedded prompt + optional nutrition goals into a shortlist of recipes.

Retrieval: top-N recipes by pgvector cosine similarity against the prompt's
embedding. Re-ranking: if the user has any nutrition goals set, narrow that
shortlist further by closeness to those goals.
"""

from pgvector.django import CosineDistance

from accounts.models import Profile
from recipes.models import Recipe

# Goals are stored as daily targets; recipes are scored per serving. Scoring
# assumes a recipe should account for roughly one meal's share of the day.
MEALS_PER_DAY_ASSUMPTION = 3

GOAL_TO_RECIPE_FIELD = {
    "daily_calorie_target": "calories_per_serving",
    "protein_target_g": "protein_g_per_serving",
    "carbs_target_g": "carbs_g_per_serving",
    "fat_target_g": "fat_g_per_serving",
    "fiber_target_g": "fiber_g_per_serving",
}


def retrieve_by_similarity(query_embedding: list[float], limit: int) -> list[Recipe]:
    # Recipes loaded but not yet embedded (backfill_embeddings pending) are skipped.
    recipes = Recipe.objects.filter(embedding__isnull=False)
    return list(recipes.order_by(CosineDistance("embedding", query_embedding))[:limit])


def _goal_closeness_score(recipe: Recipe, profile: Profile) -> float:
    """Lower is better. Averages the relative deviation between each set
    goal's per-meal share and the recipe's per-serving value. Recipes with no
    scorable overlap sort last."""
    deviations = []
    for goal_field, recipe_field in GOAL_TO_RECIPE_FIELD.items():
        target = getattr(profile, goal_field)
        value = getattr(recipe, recipe_field)
        if target is None or value is None or target == 0:
            continue
        per_meal_target = target / MEALS_PER_DAY_ASSUMPTION
        deviations.append(abs(value - per_meal_target) / per_meal_target)
    return sum(deviations) / len(deviations) if deviations else float("inf")


def rerank_by_goals(candidates: list[Recipe], profile: Profile, limit: int) -> list[Recipe]:
    return sorted(candidates, key=lambda recipe: _goal_closeness_score(recipe, profile))[:limit]


def select_candidates(
    query_embedding: list[float], profile: Profile | None, candidate_count: int, reranked_count: int
) -> list[Recipe]:
    candidates = retrieve_by_similarity(query_embedding, candidate_count)

    if profile is not None and profile.has_goals():
        return rerank_by_goals(candidates, profile, reranked_count)
    return candidates[:reranked_count]
