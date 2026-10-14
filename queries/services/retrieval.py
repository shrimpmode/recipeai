"""Recipe search for AI search: one `SearchLevel` (queries/services/targets.py) in, recipes out.

The level's nutrition limits filter the whole corpus in SQL on the per-serving
columns, and what passes is ordered by pgvector cosine similarity to the
prompt's embedding. Ranking against the targets happens in the resolver, over
every level's results together.
"""

from django.db import connection, transaction
from pgvector.django import CosineDistance

from queries.services.targets import RECIPE_FIELD, Nutrient, SearchLevel, bounds
from recipes.models import Recipe


def search_level(query_embedding: list[float], level: SearchLevel, limit: int) -> list[Recipe]:
    # Recipes loaded but not yet embedded (backfill_embeddings pending) are skipped.
    recipes = Recipe.objects.filter(embedding__isnull=False)
    for target, tolerance in level.limits:
        field = RECIPE_FIELD[target.nutrient]
        low, high = bounds(target, tolerance)
        if low is not None:
            recipes = recipes.filter(**{f"{field}__gte": low})
        if high is not None:
            recipes = recipes.filter(**{f"{field}__lte": high})
    with transaction.atomic(), connection.cursor() as cursor:
        # The HNSW index otherwise filters only its first ~40 neighbours, so a selective limit
        # returns too few rows; keep scanning until `limit` pass (pgvector >= 0.8).
        cursor.execute("SET LOCAL hnsw.iterative_scan = strict_order")
        return list(recipes.order_by(CosineDistance("embedding", query_embedding))[:limit])


def nutrient_values(recipe: Recipe) -> dict[Nutrient, float | None]:
    return {nutrient: getattr(recipe, field) for nutrient, field in RECIPE_FIELD.items()}
