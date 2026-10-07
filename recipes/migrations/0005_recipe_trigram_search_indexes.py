from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.operations import AddIndexConcurrently, TrigramExtension
from django.db import migrations, models
from django.db.models.functions import Cast, Upper


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY can't run inside a transaction; building
    # concurrently keeps recipes writable (~2 s each on the 38k corpus).
    atomic = False

    dependencies = [
        ("recipes", "0004_recipe_embedding_hnsw"),
    ]

    operations = [
        # pg_trgm ships with Postgres contrib and is a trusted extension (PG13+),
        # so the app's database owner can create it.
        TrigramExtension(),
        AddIndexConcurrently(
            model_name="recipe",
            index=GinIndex(OpClass(Upper("recipe_name"), name="gin_trgm_ops"), name="recipe_name_trgm"),
        ),
        AddIndexConcurrently(
            model_name="recipe",
            index=GinIndex(
                OpClass(
                    Upper(Cast("ingredient_lines", output_field=models.TextField())),
                    name="gin_trgm_ops",
                ),
                name="recipe_ingredients_trgm",
            ),
        ),
        migrations.RunSQL("ANALYZE recipes_recipe", reverse_sql=migrations.RunSQL.noop),
    ]
