from django.core.management.base import BaseCommand, CommandError

from recipes.models import Recipe
from recipes.services import dataset as dataset_service
from recipes.services import embeddings as embeddings_service


class Command(BaseCommand):
    help = "Ingest a curated batch of recipes from the source dataset and generate embeddings for them."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100, help="Number of recipes to ingest.")

    def handle(self, *args, **options):
        limit = options["limit"]

        self.stdout.write("Loading source dataset...")
        raw_df = dataset_service.load_raw_dataset()

        self.stdout.write(f"Selecting a curated batch of up to {limit} recipes...")
        batch_df = dataset_service.select_curated_batch(raw_df, limit)

        rows_fields = [dataset_service.parse_row_to_recipe_fields(row) for _, row in batch_df.iterrows()]
        texts = [dataset_service.compose_embedding_text(fields) for fields in rows_fields]

        self.stdout.write(f"Generating embeddings for {len(texts)} recipes...")
        embeddings = embeddings_service.embed_documents(texts)

        if len(embeddings) != len(rows_fields):
            raise CommandError(
                f"Expected {len(rows_fields)} embeddings from the embeddings API, got {len(embeddings)}."
            )

        created, updated = 0, 0
        for fields, embedding in zip(rows_fields, embeddings, strict=True):
            _, was_created = Recipe.objects.update_or_create(
                recipe_name=fields["recipe_name"],
                source_url=fields["source_url"],
                defaults={**fields, "embedding": embedding},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Ingested {created} new recipes, updated {updated} existing recipes."))
