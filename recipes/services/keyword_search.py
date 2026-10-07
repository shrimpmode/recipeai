"""Plain keyword search over recipe names and ingredients, with no AI involved.

Every whitespace-separated term must appear (case-insensitively) in the recipe
name or in at least one ingredient line. Recipes whose name contains every
term rank first. Recipes without embeddings are included: this path never
touches vectors.

Served by the pg_trgm GIN indexes `recipe_name_trgm` and
`recipe_ingredients_trgm` (migration 0005, docs/adr/0002). Two cases still
scan the table, by design: terms shorter than 3 characters (no trigrams), and
terms so common that Postgres judges a scan cheaper (e.g. "salt", in ~60% of
recipes).
"""

from django.db.models import Case, IntegerField, Q, QuerySet, Value, When

from recipes.models import Recipe, ingredients_as_text

# Bounds the size of the generated WHERE clause; extra terms are ignored.
MAX_TERMS = 8


def search_terms(query: str) -> list[str]:
    return query.split()[:MAX_TERMS]


def matching_recipes(query: str) -> QuerySet[Recipe]:
    """Every match for `query`, best first. Callers slice it."""
    terms = search_terms(query)
    if not terms:
        return Recipe.objects.none()

    matches_every_term = Q()
    name_has_every_term = Q()
    for term in terms:
        # jsonb::text is the list as JSON (e.g. ["1 cup oats", ...]), which is enough for a substring match.
        matches_every_term &= Q(recipe_name__icontains=term) | Q(ingredients_text__icontains=term)
        name_has_every_term &= Q(recipe_name__icontains=term)

    return (
        Recipe.objects.annotate(ingredients_text=ingredients_as_text())
        .filter(matches_every_term)
        .annotate(rank=Case(When(name_has_every_term, then=Value(0)), default=Value(1), output_field=IntegerField()))
        .defer("embedding")
        .order_by("rank", "recipe_name", "id")
    )


def search_recipes(query: str, limit: int) -> list[Recipe]:
    return list(matching_recipes(query)[:limit])
