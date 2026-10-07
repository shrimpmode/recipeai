# 0002 — Keyword search: ILIKE served by pg_trgm GIN indexes

Date: 2026-10-07 · Status: accepted

## Context

Keyword search (`recipes.services.keyword_search`, `GET /search/`) matches each term as a case-insensitive substring of the recipe name or the ingredient lines. Unindexed, every search scanned the whole `recipes_recipe` heap (220 MB for 38k rows, since each row stores its 1.5 KB embedding inline): ~160 ms of database time per search regardless of the term, growing linearly with the corpus.

Measured on the 38k corpus (EXPLAIN ANALYZE, indexes built in a rolled-back transaction):

| query | matches | scan | trigram index |
|---|---|---|---|
| `zzzz` | 0 | 163 ms | 0.03 ms |
| `saffron` | 191 | 166 ms | 3 ms |
| `quinoa kale` | 27 | 159 ms | 6 ms |
| `chicken` | 4,878 | 158 ms | 40 ms |
| `salt` | 23,263 | 172 ms | 173 ms (planner keeps the scan) |

## Decision

Two GIN indexes with `gin_trgm_ops` on exactly the expressions Django's `icontains` compiles to: `UPPER(recipe_name)` and `UPPER(ingredient_lines::text)`. The ingredient expression lives in one place (`recipes.models.ingredients_as_text`) and a test asserts the planner can use both indexes, because an expression mismatch fails silently as a full scan.

Rejected for now: Postgres full-text search (`tsvector` + GIN). It gives stemming and relevance ranking but changes matching semantics (whole words, not substrings), needs a maintained `tsvector` column, and would be a product change to search behaviour, not just a performance one.

## Consequences

- Selective searches drop to single-digit milliseconds; a search with no matches is instant.
- Terms under 3 characters and very common terms still scan: correct, not a regression.
- 21 MB of index (4 MB name, 17 MB ingredients), ~2 s each to build concurrently; `load_corpus` merges pay GIN maintenance on updated rows.
- Ranking is still "name contains every term, then alphabetical". If relevance ordering becomes a requirement, revisit full-text search or `similarity()` ordering.
