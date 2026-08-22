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
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py embed_recipes --limit 100
```

Then visit http://localhost:8000/, log in, set nutrition goals under "Profile", and submit a query.

### Running tests

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
docker compose up -d db redis
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test
```

Tests need a real Postgres with the `pgvector` extension (via `docker compose up -d db`) since recipe embeddings use a `VectorField`; the Claude API call is mocked in tests (embeddings run locally via sentence-transformers), so no API keys are required to run the suite.
