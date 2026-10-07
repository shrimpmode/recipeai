from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations
from pgvector.django import HnswIndex


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY can't run inside a transaction. Building it
    # concurrently keeps the table writable; apply this after the first full
    # `backfill_embeddings` so the graph is built once over complete data
    # (see README "Loading the full dataset").
    atomic = False

    dependencies = [
        ("recipes", "0003_ingestion_run_and_embedding_metadata"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="recipe",
            index=HnswIndex(
                name="recipe_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
        migrations.RunSQL("ANALYZE recipes_recipe", reverse_sql=migrations.RunSQL.noop),
    ]
