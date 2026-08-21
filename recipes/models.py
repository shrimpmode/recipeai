from django.conf import settings
from django.db import models
from pgvector.django import VectorField


class Recipe(models.Model):
    """A recipe seeded from the source dataset via `manage.py embed_recipes`.

    Nutrition fields are per-serving: the source dataset stores whole-recipe
    totals, so ingestion divides by `servings` before persisting.
    """

    recipe_name = models.CharField(max_length=500)
    source_url = models.URLField(max_length=1000, blank=True)
    image_url = models.URLField(max_length=1000, null=True, blank=True)
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

    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSIONS)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["recipe_name", "source_url"], name="unique_recipe_name_source_url"),
        ]

    def __str__(self) -> str:
        return self.recipe_name
