from pathlib import Path

from django.core.management.base import BaseCommand

from recipes.services import corpus_load, dataset


class Command(BaseCommand):
    help = (
        "Load every row of the pinned source dataset into recipes (no embeddings; "
        "run backfill_embeddings next). Safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("--revision", default=dataset.PARQUET_REVISION, help="Hub commit of the Parquet file.")
        parser.add_argument("--file", type=Path, help="Load this local Parquet file instead of downloading.")

    def handle(self, *args, **options):
        if options["file"]:
            path, revision = options["file"], "local"
        else:
            revision = options["revision"]
            self.stdout.write(f"Fetching {dataset.SOURCE_REPO}@{revision[:8]}...")
            path = dataset.fetch_source(revision)

        self.stdout.write(f"Loading {path}...")
        result = corpus_load.load_corpus(path, source_revision=revision, source_file=path.name)

        self.stdout.write(
            self.style.SUCCESS(
                f"Run {result.run_id}: {result.source_rows} source rows, {result.staged} staged, "
                f"{result.rejected} rejected; {result.inserted} inserted, {result.updated} updated."
            )
        )
        if result.rejected:
            self.stdout.write(
                f"Reasons: SELECT reason, count(*) FROM ingestion_reject WHERE run_id = {result.run_id} GROUP BY 1;"
            )
