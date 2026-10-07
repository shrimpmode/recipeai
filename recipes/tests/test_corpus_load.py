"""Full-corpus load (`load_corpus`) and the embedding backfill
(`backfill_embeddings`), run against the real Postgres + pgvector database.

The source dataset is replaced by a small Parquet file written per test with
the same column types as the published one (JSON-ish columns are strings).
The embedding model is replaced by a deterministic fake passed in through the
`Embedder` interface; nothing is patched.
"""

import json
import tempfile
from io import StringIO
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase

from recipes.models import IngestionRun, Recipe
from recipes.services import corpus_load, dataset
from recipes.services.embedding_backfill import backfill_embeddings


def _row(
    name: str,
    url_suffix: str,
    *,
    calories: float | None = 400.0,
    servings: float = 2.0,
    ingredients: tuple[str, ...] = ("1 cup oats",),
) -> dict:
    return {
        "recipe_name": name,
        "url": f"https://example.com/{url_suffix}",
        "image_url": f"https://example.com/{url_suffix}.jpg",
        "servings": servings,
        "calories": calories,
        "total_nutrients": json.dumps(
            {
                "PROCNT": {"quantity": 20.0, "unit": "g"},
                "FAT": {"quantity": 10.0, "unit": "g"},
                "CHOCDF": {"quantity": 50.0, "unit": "g"},
                "FIBTG": {"quantity": 8.0, "unit": "g"},
                "SUGAR": {"quantity": 6.0, "unit": "g"},
                "NA": {"quantity": 300.0, "unit": "mg"},
            }
        ),
        "diet_labels": json.dumps(["Balanced"]),
        "health_labels": json.dumps(["Vegetarian"]),
        "cautions": json.dumps([]),
        "cuisine_type": json.dumps(["american"]),
        "meal_type": json.dumps(["breakfast"]),
        "dish_type": json.dumps(["cereals"]),
        "ingredient_lines": json.dumps(list(ingredients)),
    }


class FakeEmbedder:
    def __init__(self, model_id: str = "fake-model", fail_on_call: int | None = None):
        self.model_id = model_id
        self.fail_on_call = fail_on_call
        self.calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError("embedder unavailable")
        return [[0.1] * settings.EMBEDDING_DIMENSIONS for _ in texts]


class ParquetFixtureMixin:
    def setUp(self):
        super().setUp()  # type: ignore[misc]
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)  # type: ignore[attr-defined]

    def write_parquet(self, rows: list[dict], name: str = "source.parquet") -> Path:
        path = Path(self._tmp.name) / name
        pq.write_table(pa.Table.from_pylist(rows), path)
        return path

    def load(self, path: Path) -> corpus_load.LoadResult:
        return corpus_load.load_corpus(path, source_revision="test-revision", source_file=path.name)


class ValidatedFieldsTests(SimpleTestCase):
    def test_valid_row_parses_to_per_serving_fields(self):
        fields = corpus_load.validated_fields(_row("Oats", "oats"))

        self.assertEqual(fields["recipe_name"], "Oats")
        self.assertEqual(fields["calories_per_serving"], 200.0)
        self.assertEqual(fields["fiber_g_per_serving"], 4.0)

    def test_missing_required_column_is_rejected(self):
        with self.assertRaisesRegex(corpus_load.RowRejected, "calories"):
            corpus_load.validated_fields(_row("Oats", "oats", calories=None))

    def test_nan_counts_as_missing(self):
        with self.assertRaisesRegex(corpus_load.RowRejected, "calories"):
            corpus_load.validated_fields(_row("Oats", "oats", calories=float("nan")))

    def test_non_positive_servings_is_rejected(self):
        with self.assertRaisesRegex(corpus_load.RowRejected, "servings"):
            corpus_load.validated_fields(_row("Oats", "oats", servings=0))

    def test_name_longer_than_column_is_rejected(self):
        with self.assertRaisesRegex(corpus_load.RowRejected, "recipe_name"):
            corpus_load.validated_fields(_row("x" * 501, "oats"))

    def test_overlong_image_url_is_dropped_not_rejected(self):
        row = _row("Oats", "oats") | {"image_url": "https://example.com/" + "i" * 1000}

        self.assertIsNone(corpus_load.validated_fields(row)["image_url"])


class EmbeddingTextHashTests(SimpleTestCase):
    def test_hash_is_stable_and_tracks_the_embedded_text(self):
        fields = corpus_load.validated_fields(_row("Oats", "oats"))
        changed = corpus_load.validated_fields(_row("Oats", "oats", ingredients=("1 cup rice",)))

        self.assertEqual(dataset.embedding_input_hash(fields), dataset.embedding_input_hash(dict(fields)))
        self.assertNotEqual(dataset.embedding_input_hash(fields), dataset.embedding_input_hash(changed))


class LoadCorpusTests(ParquetFixtureMixin, TestCase):
    def test_load_reconciles_dedupes_and_records_rejects(self):
        path = self.write_parquet(
            [
                _row("Oats", "oats"),
                _row("Salad", "salad"),
                _row("Oats", "oats-other-site"),  # same name: first occurrence wins
                _row("Broken", "broken", calories=None),
            ]
        )

        result = self.load(path)

        self.assertEqual((result.source_rows, result.staged, result.rejected), (4, 3, 1))
        self.assertEqual((result.inserted, result.updated), (2, 0))
        self.assertEqual(
            set(Recipe.objects.values_list("recipe_name", "source_url")),
            {("Oats", "https://example.com/oats"), ("Salad", "https://example.com/salad")},
        )
        self.assertFalse(Recipe.objects.filter(embedding__isnull=False).exists())

        run = IngestionRun.objects.get(id=result.run_id)
        self.assertEqual(run.status, IngestionRun.Status.SUCCEEDED)
        self.assertEqual((run.source_rows, run.staged_rows, run.rejected_rows), (4, 3, 1))
        self.assertEqual(run.source_revision, "test-revision")
        self.assertEqual(len(run.file_sha256), 64)
        self.assertTrue(Recipe.objects.filter(last_seen_run=run).count() == 2)

        with connection.cursor() as cursor:
            cursor.execute("SELECT row_number, reason FROM ingestion_reject WHERE run_id = %s", [run.id])
            rejects = cursor.fetchall()
            cursor.execute("SELECT count(*) FROM recipe_staging")
            staging_rows_left = cursor.fetchone()[0]
        self.assertEqual(len(rejects), 1)
        self.assertEqual(rejects[0][0], 4)
        self.assertIn("calories", rejects[0][1])
        self.assertEqual(staging_rows_left, 0)

    def test_reloading_the_same_file_keeps_embeddings(self):
        path = self.write_parquet([_row("Oats", "oats"), _row("Salad", "salad")])
        self.load(path)
        backfill_embeddings(FakeEmbedder())
        embedded_at_before = dict(Recipe.objects.values_list("id", "embedded_at"))

        result = self.load(path)

        self.assertEqual((result.inserted, result.updated), (0, 2))
        self.assertFalse(Recipe.objects.filter(embedding__isnull=True).exists())
        self.assertEqual(dict(Recipe.objects.values_list("id", "embedded_at")), embedded_at_before)

    def test_changed_embedding_text_clears_only_that_rows_embedding(self):
        self.load(self.write_parquet([_row("Oats", "oats"), _row("Salad", "salad")], "v1.parquet"))
        backfill_embeddings(FakeEmbedder())

        self.load(
            self.write_parquet(
                [_row("Oats", "oats"), _row("Salad", "salad", ingredients=("2 cups kale",))], "v2.parquet"
            )
        )

        self.assertIsNotNone(Recipe.objects.get(recipe_name="Oats").embedding)
        salad = Recipe.objects.get(recipe_name="Salad")
        self.assertIsNone(salad.embedding)
        self.assertEqual(salad.ingredient_lines, ["2 cups kale"])

    def test_command_reports_the_run(self):
        path = self.write_parquet([_row("Oats", "oats")])
        out = StringIO()

        call_command("load_corpus", "--file", str(path), stdout=out)

        self.assertIn("1 staged, 0 rejected", out.getvalue())
        self.assertEqual(Recipe.objects.count(), 1)


class BackfillEmbeddingsTests(ParquetFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.load(self.write_parquet([_row(f"Recipe {i}", f"r{i}") for i in range(5)]))

    def test_embeds_every_stale_row_in_batches(self):
        embedder = FakeEmbedder()

        embedded = backfill_embeddings(embedder, batch_size=2)

        self.assertEqual(embedded, 5)
        self.assertEqual(embedder.calls, 3)
        self.assertFalse(Recipe.objects.filter(embedding__isnull=True).exists())
        self.assertEqual(set(Recipe.objects.values_list("embedding_model", flat=True)), {"fake-model"})
        self.assertEqual(backfill_embeddings(embedder), 0)

    def test_resumes_after_a_failure_mid_run(self):
        with self.assertRaises(RuntimeError):
            backfill_embeddings(FakeEmbedder(fail_on_call=2), batch_size=2)
        self.assertEqual(Recipe.objects.filter(embedding__isnull=False).count(), 2)

        resumed = FakeEmbedder()
        self.assertEqual(backfill_embeddings(resumed, batch_size=2), 3)
        self.assertEqual(resumed.calls, 2)

    def test_switching_models_reembeds_everything(self):
        backfill_embeddings(FakeEmbedder(model_id="model-a"))

        self.assertEqual(backfill_embeddings(FakeEmbedder(model_id="model-b")), 5)
        self.assertEqual(set(Recipe.objects.values_list("embedding_model", flat=True)), {"model-b"})

    def test_stored_hash_matches_what_a_load_computes(self):
        backfill_embeddings(FakeEmbedder())
        hashes_after_backfill = dict(Recipe.objects.values_list("id", "embedding_input_hash"))

        self.load(self.write_parquet([_row(f"Recipe {i}", f"r{i}") for i in range(5)], "again.parquet"))

        self.assertEqual(dict(Recipe.objects.values_list("id", "embedding_input_hash")), hashes_after_backfill)
        self.assertFalse(Recipe.objects.filter(embedding__isnull=True).exists())


class VectorIndexTests(TestCase):
    def test_hnsw_cosine_index_exists(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexdef FROM pg_indexes WHERE tablename = 'recipes_recipe' AND indexname = %s",
                ["recipe_embedding_hnsw"],
            )
            row = cursor.fetchone()

        assert row is not None
        self.assertIn("hnsw", row[0])
        self.assertIn("vector_cosine_ops", row[0])
