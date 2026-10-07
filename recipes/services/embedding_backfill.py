"""Fill in recipe embeddings after `corpus_load`, resumably.

The database is the work queue: a recipe needs embedding when `embedding` is
NULL or `embedding_model` isn't the current model. Batches are read in id
order (keyset pagination), embedded with no transaction open, then written and
committed one batch at a time, so an interrupted run loses at most one batch
and re-running picks up where it stopped. Switching models is the same call.
"""

import logging
from collections.abc import Callable
from typing import Protocol

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from recipes.models import Recipe
from recipes.services import dataset

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    model_id: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingCountMismatch(RuntimeError):
    pass


def backfill_embeddings(
    embedder: Embedder,
    batch_size: int = 512,
    on_batch: Callable[[int], None] | None = None,
) -> int:
    """Embed every stale recipe; returns how many were embedded. `on_batch`
    receives the running total after each committed batch."""
    stale = Q(embedding__isnull=True) | ~Q(embedding_model=embedder.model_id)
    last_id = embedded = 0
    while True:
        batch = list(
            Recipe.objects.filter(stale, id__gt=last_id)
            .order_by("id")
            .only("id", *dataset.EMBEDDING_TEXT_FIELDS)[:batch_size]
        )
        if not batch:
            return embedded

        texts = [
            dataset.compose_embedding_text({f: getattr(r, f) for f in dataset.EMBEDDING_TEXT_FIELDS}) for r in batch
        ]
        vectors = embedder.embed_documents(texts)
        if len(vectors) != len(batch):
            raise EmbeddingCountMismatch(f"asked for {len(batch)} embeddings, got {len(vectors)}")

        now = timezone.now()
        for recipe, text, vector in zip(batch, texts, vectors, strict=True):
            recipe.embedding = vector
            recipe.embedding_input_hash = dataset.embedding_text_hash(text)
            recipe.embedding_model = embedder.model_id
            recipe.embedded_at = now
        with transaction.atomic():
            Recipe.objects.bulk_update(batch, ["embedding", "embedding_input_hash", "embedding_model", "embedded_at"])

        last_id = batch[-1].id
        embedded += len(batch)
        logger.info("embedding_batch_committed", extra={"last_id": last_id, "embedded": embedded})
        if on_batch is not None:
            on_batch(embedded)
