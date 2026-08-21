## Nutrition Project

This is a project to implement a very simple RAG flow, the stack will be Django, Docker, Postgres, Anthropic API, Celery if Needed 
A user can have a profile and can set nutrition goals 
A user can set a prompt that would be like something they want to eat or achieve
This is not a chat, just a user input that waits for a response

<example id="high fiber diet example">
Today I would like to eat something high fiber
</example>

<example id="high protein diet example">
How can my breakfasts be high protein
</example>


the backend can use a rag flow to resolve the users query 

the ui keeps waiting and loading and after the query is resolved it shows 3 recipes , and their descriptions 


## Rag
we will use this dataset 
import pandas as pd

df = pd.read_csv("hf://datasets/datahiveai/recipes-with-nutrition/recipes-with-nutrition.csv")

We will have an admin to create embeddings, but not from the entire dataset 
Lets start with 100 rows first 

## Running locally

See `specs/rag-nutrition-mvp.md` for the full design spec.

```
cp .env.example .env   # fill in ANTHROPIC_API_KEY and VOYAGE_API_KEY
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

Tests need a real Postgres with the `pgvector` extension (via `docker compose up -d db`) since recipe embeddings use a `VectorField`; the external Voyage/Claude API calls are mocked in tests, so no API keys are required to run the suite.
