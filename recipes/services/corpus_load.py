"""Bulk load of the full source dataset into `recipes_recipe`.

Pinned Parquet file -> parse/validate each row (rules in `dataset.py`) ->
COPY into `recipe_staging` -> one set-based upsert into `recipes_recipe`.
Rows that can't become a Recipe go to `ingestion_reject` with a reason, and
the run fails unless source rows = staged + rejected.

Embeddings are not computed here. A recipe's embedding is cleared only when
the text it is embedded from changes; `embedding_backfill` fills in the rest.
"""

import hashlib
import logging
import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq
from django.db import connection, models, transaction
from django.utils import timezone
from psycopg.types.json import Jsonb

from recipes.models import IngestionRun, Recipe
from recipes.services import dataset

logger = logging.getLogger(__name__)

LOCK_NAME = "recipes.load_corpus"

KEY_COLUMNS = ("recipe_name", "source_url")
NUTRITION_COLUMNS = ("calories_per_serving", *dataset.NUTRIENT_TAG_MAP)
JSON_COLUMNS = (
    "ingredient_lines",
    "diet_labels",
    "health_labels",
    "cautions",
    "cuisine_type",
    "meal_type",
    "dish_type",
)
DATA_COLUMNS = ("image_url", "servings", *NUTRITION_COLUMNS, *JSON_COLUMNS)
STAGING_COLUMNS = ("run_id", "row_number", *KEY_COLUMNS, *DATA_COLUMNS, "embedding_input_hash")


def _max_length(field_name: str) -> int:
    field = Recipe._meta.get_field(field_name)
    assert isinstance(field, models.CharField) and field.max_length is not None
    return field.max_length


_MAX_LENGTHS = {name: _max_length(name) for name in ("recipe_name", "source_url", "image_url")}


class RowRejected(ValueError):
    """A source row that can't become a Recipe. Recorded, never fatal to the run."""


class LoadInProgress(RuntimeError):
    """Another `load_corpus` holds the advisory lock."""


class ReconciliationError(RuntimeError):
    """Source rows != staged + rejected: some rows were lost, so the run is aborted."""


@dataclass(frozen=True)
class LoadResult:
    run_id: int
    source_rows: int
    staged: int
    rejected: int
    inserted: int
    updated: int


def load_corpus(parquet_path: Path, *, source_revision: str, source_file: str, batch_size: int = 2_000) -> LoadResult:
    """Load every row of `parquet_path` in one transaction. Safe to re-run:
    a second load of the same file inserts nothing and keeps all embeddings."""
    with _exclusive_load_lock():
        run = IngestionRun.objects.create(
            source_repo=dataset.SOURCE_REPO,
            source_revision=source_revision,
            source_file=source_file,
            file_sha256=_sha256(parquet_path),
            source_rows=pq.ParquetFile(parquet_path).metadata.num_rows,
        )
        log_context = {"run_id": run.id, "source_rows": run.source_rows}
        logger.info("corpus_load_started", extra=log_context)
        try:
            with transaction.atomic():
                staged, rejected = _stage(run.id, parquet_path, batch_size)
                if staged + rejected != run.source_rows:
                    raise ReconciliationError(
                        f"{run.source_rows} source rows but {staged} staged + {rejected} rejected"
                    )
                inserted, updated = _merge(run.id)
                _clear_staging(run.id)

                run.staged_rows, run.rejected_rows = staged, rejected
                run.inserted_rows, run.updated_rows = inserted, updated
                run.status = IngestionRun.Status.SUCCEEDED
                run.finished_at = timezone.now()
                run.save()
        except Exception as exc:
            IngestionRun.objects.filter(id=run.id).update(
                status=IngestionRun.Status.FAILED, error_message=str(exc), finished_at=timezone.now()
            )
            logger.exception("corpus_load_failed", extra=log_context)
            raise

    logger.info(
        "corpus_load_succeeded",
        extra=log_context | {"staged": staged, "rejected": rejected, "inserted": inserted, "updated": updated},
    )
    return LoadResult(run.id, run.source_rows, staged, rejected, inserted, updated)


def validated_fields(raw: dict) -> dict:
    """Recipe fields for one source row, or RowRejected explaining why not."""
    missing = [column for column in dataset.REQUIRED_COLUMNS if _is_missing(raw.get(column))]
    if missing:
        raise RowRejected(f"missing required columns: {', '.join(missing)}")
    if raw["servings"] <= 0:
        raise RowRejected(f"servings must be positive, got {raw['servings']}")

    fields = dataset.parse_row_to_recipe_fields(raw)
    for column in KEY_COLUMNS:
        if len(fields[column]) > _MAX_LENGTHS[column]:
            raise RowRejected(f"{column} longer than {_MAX_LENGTHS[column]} characters")
    # A broken image link shouldn't cost us the recipe.
    if fields["image_url"] and len(fields["image_url"]) > _MAX_LENGTHS["image_url"]:
        fields["image_url"] = None
    return fields


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


@contextmanager
def _exclusive_load_lock() -> Iterator[None]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [LOCK_NAME])
        (acquired,) = cursor.fetchone()
    if not acquired:
        raise LoadInProgress("another load_corpus run holds the lock")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [LOCK_NAME])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage(run_id: int, parquet_path: Path, batch_size: int) -> tuple[int, int]:
    rejects: list[tuple] = []
    staged = row_number = 0
    with connection.cursor() as cursor:
        with cursor.copy(f"COPY recipe_staging ({', '.join(STAGING_COLUMNS)}) FROM STDIN") as copy:
            for batch in pq.ParquetFile(parquet_path).iter_batches(batch_size=batch_size):
                for raw in batch.to_pylist():
                    row_number += 1
                    try:
                        fields = validated_fields(raw)
                    except ValueError as exc:  # RowRejected, or a parse error from dataset.py
                        rejects.append((run_id, row_number, str(exc), Jsonb(_json_safe(raw))))
                        continue
                    copy.write_row(_staging_row(run_id, row_number, fields))
                    staged += 1
                logger.info("corpus_load_batch_staged", extra={"run_id": run_id, "rows_read": row_number})
        if rejects:
            cursor.executemany(
                "INSERT INTO ingestion_reject (run_id, row_number, reason, raw) VALUES (%s, %s, %s, %s)", rejects
            )
    return staged, len(rejects)


def _staging_row(run_id: int, row_number: int, fields: dict) -> tuple:
    return (
        run_id,
        row_number,
        *(fields[column] for column in KEY_COLUMNS),
        *(Jsonb(fields[column]) if column in JSON_COLUMNS else fields[column] for column in DATA_COLUMNS),
        dataset.embedding_input_hash(fields),
    )


def _json_safe(raw: dict) -> dict:
    # jsonb rejects NaN, which pyarrow can hand us for float columns.
    return {key: None if _is_missing(value) else value for key, value in raw.items()}


def _merge(run_id: int) -> tuple[int, int]:
    """Upsert staged rows. DISTINCT ON keeps the first occurrence of each
    recipe name (the same dedupe rule `embed_recipes` uses). An existing
    embedding survives only if its input hash is unchanged."""
    insert_columns = ", ".join((*KEY_COLUMNS, *DATA_COLUMNS, "embedding_input_hash"))
    updates = ",\n            ".join(f"{column} = EXCLUDED.{column}" for column in DATA_COLUMNS)
    sql = f"""
        INSERT INTO {Recipe._meta.db_table} AS r (
            {insert_columns}, embedding_model, last_seen_run_id, created_at
        )
        SELECT DISTINCT ON (recipe_name) {insert_columns}, '', run_id, now()
        FROM recipe_staging
        WHERE run_id = %s
        ORDER BY recipe_name, row_number
        ON CONFLICT (recipe_name, source_url) DO UPDATE SET
            {updates},
            last_seen_run_id = EXCLUDED.last_seen_run_id,
            embedding = CASE WHEN r.embedding_input_hash = EXCLUDED.embedding_input_hash
                             THEN r.embedding ELSE NULL END,
            embedding_input_hash = EXCLUDED.embedding_input_hash
        RETURNING (xmax = 0) AS inserted
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [run_id])
        outcomes = [inserted for (inserted,) in cursor.fetchall()]
    inserted = sum(outcomes)
    return inserted, len(outcomes) - inserted


def _clear_staging(run_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM recipe_staging WHERE run_id = %s", [run_id])
