from django.core.management.base import BaseCommand

from recipes.services.embedding_backfill import backfill_embeddings
from recipes.services.embeddings import LocalEmbedder


class Command(BaseCommand):
    help = "Embed every recipe whose embedding is missing or from another model. Interrupt-safe; re-run to resume."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=512)

    def handle(self, *args, **options):
        embedder = LocalEmbedder()
        self.stdout.write(f"Embedding stale recipes with {embedder.model_id}...")
        total = backfill_embeddings(
            embedder,
            batch_size=options["batch_size"],
            on_batch=lambda done: self.stdout.write(f"  {done} embedded"),
        )
        self.stdout.write(self.style.SUCCESS(f"Embedded {total} recipes."))
