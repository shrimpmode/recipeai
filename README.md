# Nutrition Goal RAG

A small Django app that turns a free-text prompt like *"something high fiber"* into 3 recipe recommendations, screened against a user's personal nutrition goals (calories, protein, carbs, fat, fiber) — not just keyword-matched.

## What it does

1. A user sets optional nutrition goals on their profile (daily calorie/protein/carbs/fat/fiber targets).
2. They type a free-text prompt describing what they want to eat.
3. A background worker runs a small RAG pipeline:
   - embeds the prompt with a local `sentence-transformers` model
   - retrieves the closest recipes from a Postgres/`pgvector` corpus by cosine similarity
   - if the user has goals set, re-ranks those candidates by nutritional closeness to their targets
   - hands the shortlist to Claude Haiku, which picks and writes a short description for the final 3
4. The page polls until the result is ready and shows 3 recipes with descriptions, per-serving nutrition stats, and a link back to the source.

## Why it's built this way

- **Async by design** — query resolution (embed → retrieve → rerank → generate) runs on a Celery worker, not the request thread, so slow embedding/LLM calls can't time out a web request.
- **Goals are optional, retrieval isn't** — with no profile goals set, results fall back to pure semantic similarity; goals only kick in to re-rank, they never gate a user out of results.
- **Always exactly 3 results** — the task enforces this explicitly (see `queries/tasks.py`) rather than trusting the LLM's output shape, and retries transient embedding/Claude failures a few times before surfacing an error state.
- **Embeddings run locally** — no API key or per-query cost for the retrieval step; only the final selection/description call goes to Claude.

## Stack

Django · Postgres + `pgvector` · Redis + Celery · `sentence-transformers` (`all-MiniLM-L6-v2`) · Anthropic Claude Haiku · HTMX · Tailwind · Docker Compose

See [`specs/rag-nutrition-mvp.md`](specs/rag-nutrition-mvp.md) for the full design spec (user stories, data model, and the testing approach).

## Dataset

Seed recipes come from the [`datahiveai/recipes-with-nutrition`](https://huggingface.co/datasets/datahiveai/recipes-with-nutrition) dataset on Hugging Face:

```python
import pandas as pd

df = pd.read_csv("hf://datasets/datahiveai/recipes-with-nutrition/recipes-with-nutrition.csv")
```

The `embed_recipes` management command pulls a curated batch from this dataset (deduped, spread across meal/diet types) rather than a naive slice — see [Implementation Decisions](specs/rag-nutrition-mvp.md) for details.

## Running locally

```
cp .env.example .env   # fill in ANTHROPIC_API_KEY (embeddings run locally, no key needed)
docker compose up --build   # image installs deps from uv.lock
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py embed_recipes --limit 100   # quick dev seed
```

### Loading the full dataset

The full corpus (39,447 rows, pinned to a specific Parquet commit on the Hub) is loaded in two steps, then indexed. Every step is safe to re-run; see [ADR 0001](docs/adr/0001-corpus-load-pipeline.md).

```
docker compose exec db pg_dump -U nutrition -Fc nutrition > backup.dump   # before the first load
docker compose run --rm worker python manage.py migrate recipes 0003      # schema only, no vector index yet
docker compose run --rm worker python manage.py load_corpus               # fetch -> stage (COPY) -> merge; seconds
docker compose run --rm worker python manage.py backfill_embeddings       # slow; Ctrl-C safe, re-run to resume
docker compose run --rm worker python manage.py migrate                   # HNSW index on embeddings
```

`load_corpus` records each run in `IngestionRun` (source revision, file SHA-256, row counts) and fails unless source rows = staged + rejected. Rejected rows and their reasons are in the `ingestion_reject` table. Recipes appear in search results once they have an embedding.

Then visit http://localhost:8000/, log in, set nutrition goals under "Profile", and submit a query.

### Engineering manual

Architecture, schema, vector search and operations: <http://localhost:8000/docs/> (staff users only; create one with `createsuperuser`). Source: `templates/docs/manual.html`.

### Local development

Dependencies are managed with [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`). `uv sync` creates `.venv` with the app and dev tools.

```
uv sync                          # install / update .venv from uv.lock
uv add <package>                 # add a dependency (updates pyproject.toml + uv.lock)
uv add --dev <package>           # add a dev-only tool
```

### Lint, format, type-check

```
uv run ruff format .             # format
uv run ruff check --fix .        # lint (+ safe autofixes)
uv run mypy .                    # type-check (Django plugin; the authoritative check)
```

Editors: `[tool.pyright]` in `pyproject.toml` points Pyright/basedpyright at `.venv`, so Neovim's LSP resolves imports with no extra setup. Use ruff's LSP (`ruff server`) for lint and format-on-save.

### Running tests

```
docker compose up -d db redis
POSTGRES_HOST=localhost uv run python manage.py migrate
POSTGRES_HOST=localhost uv run python manage.py test
```

Tests need a real Postgres with the `pgvector` extension (via `docker compose up -d db`) since recipe embeddings use a `VectorField`; the Claude API call is mocked in tests (embeddings run locally via sentence-transformers), so no API keys are required to run the suite.
