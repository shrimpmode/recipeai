"""Seam 2: the `embed_recipes` ingestion management command.

The only heavyweight boundary mocked is the local embedding model call
(`recipes.services.embeddings.embed_documents`); dataset loading is stubbed
via `load_raw_dataset` since it's a network call. Curation (dedupe, required
fields, dish-type diversity) and per-serving nutrition math run for real.
"""

import json
from unittest.mock import patch

import pandas as pd
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from recipes.models import Recipe


def _nutrients(protein, fat, carbs, fiber, sugar, sodium):
    return json.dumps(
        {
            "PROCNT": {"quantity": protein, "unit": "g"},
            "FAT": {"quantity": fat, "unit": "g"},
            "CHOCDF": {"quantity": carbs, "unit": "g"},
            "FIBTG": {"quantity": fiber, "unit": "g"},
            "SUGAR": {"quantity": sugar, "unit": "g"},
            "NA": {"quantity": sodium, "unit": "mg"},
        }
    )


def _row(name, dish_type, source_suffix, calories=200.0, servings=2.0, **nutrient_kwargs):
    nutrients = _nutrients(
        protein=nutrient_kwargs.get("protein", 20.0),
        fat=nutrient_kwargs.get("fat", 10.0),
        carbs=nutrient_kwargs.get("carbs", 30.0),
        fiber=nutrient_kwargs.get("fiber", 6.0),
        sugar=nutrient_kwargs.get("sugar", 8.0),
        sodium=nutrient_kwargs.get("sodium", 400.0),
    )
    return {
        "recipe_name": name,
        "url": f"https://example.com/{source_suffix}",
        "image_url": f"https://example.com/{source_suffix}.jpg",
        "servings": servings,
        "calories": calories,
        "total_nutrients": nutrients,
        "diet_labels": json.dumps(["Balanced"]),
        "health_labels": json.dumps(["Vegetarian"]),
        "cautions": json.dumps([]),
        "cuisine_type": json.dumps(["american"]),
        "meal_type": json.dumps(["dinner"]),
        "dish_type": json.dumps([dish_type]),
        "ingredient_lines": json.dumps(["1 cup broth"]),
    }


def _fake_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _row("Soup A", "soup", "soup-a"),
            _row("Soup A", "soup", "soup-a-duplicate"),  # duplicate name, dropped by dedupe
            _row("Salad B", "salad", "salad-b"),
            _row("Bowl C", "bowl", "bowl-c", calories=float("nan")),  # missing required field, dropped
            _row("Soup D", "soup", "soup-d"),
        ]
    )


def _fake_embed_documents(texts):
    return [[0.1] * settings.EMBEDDING_DIMENSIONS for _ in texts]


class EmbedRecipesCommandTests(TestCase):
    @patch("recipes.services.embeddings.embed_documents", side_effect=_fake_embed_documents)
    @patch("recipes.services.dataset.load_raw_dataset", return_value=_fake_dataframe())
    def test_curates_dedupes_and_flattens_nutrition(self, mock_load, mock_embed):
        call_command("embed_recipes", "--limit", "3")

        names = set(Recipe.objects.values_list("recipe_name", flat=True))
        self.assertEqual(names, {"Soup A", "Salad B", "Soup D"})

        soup_a = Recipe.objects.get(recipe_name="Soup A")
        self.assertEqual(soup_a.calories_per_serving, 100.0)
        self.assertEqual(soup_a.protein_g_per_serving, 10.0)
        self.assertEqual(soup_a.fat_g_per_serving, 5.0)
        self.assertEqual(soup_a.carbs_g_per_serving, 15.0)
        self.assertEqual(soup_a.fiber_g_per_serving, 3.0)
        self.assertEqual(soup_a.sugar_g_per_serving, 4.0)
        self.assertEqual(soup_a.sodium_mg_per_serving, 200.0)
        assert soup_a.embedding is not None
        self.assertEqual(len(soup_a.embedding), settings.EMBEDDING_DIMENSIONS)

    @patch("recipes.services.embeddings.embed_documents", side_effect=_fake_embed_documents)
    @patch("recipes.services.dataset.load_raw_dataset", return_value=_fake_dataframe())
    def test_rerunning_with_larger_limit_adds_without_duplicating(self, mock_load, mock_embed):
        call_command("embed_recipes", "--limit", "3")
        self.assertEqual(Recipe.objects.count(), 3)

        call_command("embed_recipes", "--limit", "10")

        # Only 3 rows in the fake dataset survive curation regardless of limit.
        self.assertEqual(Recipe.objects.count(), 3)
        self.assertEqual(
            Recipe.objects.filter(recipe_name="Soup A", source_url="https://example.com/soup-a").count(),
            1,
        )
