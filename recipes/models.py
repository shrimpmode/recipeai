from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db import models
from django.db.models.functions import Cast, Upper
from pgvector.django import HnswIndex, VectorField


def ingredients_as_text() -> Cast:
    """`ingredient_lines` (jsonb) as text, for substring search. The trigram
    index below is built on this exact expression, so keyword search must
    use it too or Postgres won't match the query to the index."""
    return Cast("ingredient_lines", output_field=models.TextField())


class IngestionRun(models.Model):
    """One execution of `manage.py load_corpus`: where the data came from and
    how every source row was accounted for (source = staged + rejected)."""

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    # Declared for Pyright, which can't see Django's implicit fields (mypy's plugin can).
    id: int

    source_repo = models.CharField(max_length=200)
    source_revision = models.CharField(max_length=64)
    source_file = models.CharField(max_length=300)
    file_sha256 = models.CharField(max_length=64)
    source_rows = models.PositiveIntegerField()
    staged_rows = models.PositiveIntegerField(default=0)
    rejected_rows = models.PositiveIntegerField(default=0)
    inserted_rows = models.PositiveIntegerField(default=0)
    updated_rows = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"IngestionRun({self.id}, {self.status})"


class Recipe(models.Model):
    """A recipe loaded from the source dataset via `manage.py load_corpus`
    (or seeded in dev via `manage.py embed_recipes`).

    Nutrition fields are per-serving: the source dataset stores whole-recipe
    totals, so ingestion divides by `servings` before persisting.

    `embedding` is NULL until `manage.py backfill_embeddings` has run for the
    row; retrieval skips such rows. A row needs (re-)embedding when its
    embedding is NULL or `embedding_model` differs from the current model.
    """

    # Declared for Pyright, which can't see Django's implicit fields (mypy's plugin can).
    id: int
    last_seen_run_id: int | None

    recipe_name = models.CharField(max_length=500)
    source_url = models.URLField(max_length=1000, blank=True)
    # TODO(schema): two empty values (NULL and ""); normalise to blank=True only via expand/migrate/contract.
    image_url = models.URLField(max_length=1000, null=True, blank=True)  # noqa: DJ001
    servings = models.FloatField()

    ingredient_lines = models.JSONField(default=list)
    diet_labels = models.JSONField(default=list)
    health_labels = models.JSONField(default=list)
    cautions = models.JSONField(default=list)
    cuisine_type = models.JSONField(default=list)
    meal_type = models.JSONField(default=list)
    dish_type = models.JSONField(default=list)

    calories_per_serving = models.FloatField(null=True, blank=True)
    protein_g_per_serving = models.FloatField(null=True, blank=True)
    carbs_g_per_serving = models.FloatField(null=True, blank=True)
    fat_g_per_serving = models.FloatField(null=True, blank=True)
    fiber_g_per_serving = models.FloatField(null=True, blank=True)
    sugar_g_per_serving = models.FloatField(null=True, blank=True)
    sodium_mg_per_serving = models.FloatField(null=True, blank=True)

    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSIONS, null=True, blank=True)
    # sha256 of the text that was (or will be) embedded; a load clears
    # `embedding` only when this changes, so unchanged rows keep their vectors.
    embedding_input_hash = models.CharField(max_length=64, blank=True)
    embedding_model = models.CharField(max_length=100, blank=True)
    embedded_at = models.DateTimeField(null=True, blank=True)
    last_seen_run = models.ForeignKey(IngestionRun, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["recipe_name", "source_url"], name="unique_recipe_name_source_url"),
        ]
        indexes = [
            # Matches the CosineDistance ordering in queries.services.retrieval.
            HnswIndex(
                name="recipe_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            # Serve keyword search's case-insensitive substring matches (Django's
            # icontains compiles to UPPER(col) LIKE UPPER(term)); see
            # recipes.services.keyword_search and docs/adr/0002.
            GinIndex(OpClass(Upper("recipe_name"), name="gin_trgm_ops"), name="recipe_name_trgm"),
            GinIndex(OpClass(Upper(ingredients_as_text()), name="gin_trgm_ops"), name="recipe_ingredients_trgm"),
        ]

    def __str__(self) -> str:
        return self.recipe_name
