# 0001 — Full-corpus load: staged COPY + separate embedding backfill

Date: 2026-10-07 · Status: accepted

## Context

We load the whole `datahiveai/recipes-with-nutrition` dataset (39,447 rows) instead of a 100-row curated sample. The old `embed_recipes` command read the 450 MB CSV over the network on every run, embedded everything in one call, and wrote rows one at a time with `update_or_create`. The embedding model has also changed three times (Voyage → OpenAI → local MiniLM), so vectors go stale independently of recipe data.

## Decision

- **Pinned source.** `load_corpus` downloads the Hub's Parquet copy at a fixed commit (`dataset.PARQUET_REVISION`) through the local HF cache, and records revision + SHA-256 on an `IngestionRun`.
- **Stage then merge.** Rows are validated in Python (`corpus_load.validated_fields`), streamed into an UNLOGGED `recipe_staging` table with `COPY`, and merged with one `INSERT … ON CONFLICT`. Invalid rows go to `ingestion_reject` with a reason. The run aborts unless source = staged + rejected.
- **Embedding is a separate, resumable job.** `backfill_embeddings` treats "embedding IS NULL or embedding_model ≠ current" as its queue, works in id-ordered batches, and commits per batch. A load clears an embedding only when `embedding_input_hash` (sha256 of the text that gets embedded) changes.
- **HNSW index** (`vector_cosine_ops`, m=16, ef_construction=64) in its own concurrent migration, applied after the first backfill.

## Consequences

- Re-running a load is cheap and keeps vectors; switching models is one `backfill_embeddings` run.
- `Recipe.embedding` is nullable; retrieval must filter `embedding IS NOT NULL` (it does).
- Recipes are invisible to search between `load_corpus` and `backfill_embeddings`.
- Staging/reject tables are raw SQL, not models.
- Dedupe keeps the first row per `recipe_name`, matching `embed_recipes`.
- Dataset license is CC BY-NC 4.0: non-commercial use only.
- At ~1M+ rows: fan the backfill out by id range on Celery, and consider `halfvec`.
