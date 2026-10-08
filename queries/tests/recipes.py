from django.conf import settings

from recipes.models import Recipe


def embedding(seed: float) -> list[float]:
    return [seed] * settings.EMBEDDING_DIMENSIONS


def make_recipe(**overrides) -> Recipe:
    defaults = {
        "recipe_name": "Recipe",
        "source_url": "https://example.com/recipe",
        "servings": 2,
        "ingredient_lines": ["stuff"],
        "diet_labels": [],
        "health_labels": [],
        "cautions": [],
        "cuisine_type": [],
        "meal_type": [],
        "dish_type": [],
        "calories_per_serving": 300,
        "protein_g_per_serving": 10,
        "carbs_g_per_serving": 30,
        "fat_g_per_serving": 10,
        "fiber_g_per_serving": 5,
        "sugar_g_per_serving": 5,
        "sodium_mg_per_serving": 200,
        "embedding": embedding(0.1),
    }
    defaults.update(overrides)
    return Recipe.objects.create(**defaults)
