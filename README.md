## Dataset
import pandas as pd

df = pd.read_csv("hf://datasets/datahiveai/recipes-with-nutrition/recipes-with-nutrition.csv")


## Running locally

See `specs/rag-nutrition-mvp.md` for the full design spec.

```
cp .env.example .env   # fill in ANTHROPIC_API_KEY and OPENAI_API_KEY
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

Tests need a real Postgres with the `pgvector` extension (via `docker compose up -d db`) since recipe embeddings use a `VectorField`; the external OpenAI/Claude API calls are mocked in tests, so no API keys are required to run the suite.
