# Nutrition Goal RAG — MVP Spec

## Problem Statement

A user who wants to eat according to a nutrition goal (e.g. "high fiber," "high protein breakfast") has to manually search recipe sites and cross-reference nutrition labels themselves. There's no single place where they can state what they want to eat or achieve, in their own words, and get back recipes that are actually screened against their personal nutrition targets.

## Solution

Users maintain a profile with optional nutrition goals (daily calorie target, protein/carbs/fat/fiber targets). They submit a free-text prompt describing what they want to eat ("something high fiber," "high protein breakfasts"). The system runs a RAG flow — semantic retrieval over a curated recipe corpus, re-ranked against the user's goals where set — and an LLM selects and describes the 3 best-matching recipes. The UI shows a loading state while this resolves, then displays the 3 recipes with descriptions, key nutrition stats, and a source link.

## User Stories

1. As a registered user, I want to create a profile, so that the system has a place to store my nutrition preferences.
2. As a registered user, I want to set a daily calorie target on my profile, so that recommendations can be screened against it.
3. As a registered user, I want to set protein/carbs/fat/fiber targets on my profile, so that recommendations can favor recipes matching my macro goals.
4. As a registered user, I want all nutrition goal fields to be optional, so that I can use the feature before I've decided on specific targets.
5. As a registered user, I want to edit my nutrition goals at any time, so that recommendations stay current as my goals change.
6. As an unauthenticated visitor, I want to be required to log in before submitting a query, so that recommendations can be personalized to my goals from the first query.
7. As a registered user, I want to type a free-text prompt describing what I want to eat or achieve, so that I don't have to learn a structured search syntax.
8. As a registered user, I want to submit my prompt and immediately see a loading state, so that I know my request is being processed.
9. As a registered user, I want the page to keep waiting/polling until my query resolves, so that I don't have to manually refresh.
10. As a registered user, I want to receive exactly 3 recipes per query, so that I get a manageable, decisive set of options rather than an overwhelming list.
11. As a registered user, I want each recipe result to include a short description explaining why it matches my prompt/goals, so that I understand the recommendation instead of just seeing a title.
12. As a registered user, I want each recipe result to show key nutrition stats (calories, protein, carbs, fat, fiber, sugar, sodium) per serving, so that I can verify it actually fits my goals.
13. As a registered user, I want a link back to the original recipe source, so that I can view full instructions and attribution.
14. As a registered user, I want to see a recipe's image when one is available, so that I have a visual reference.
15. As a registered user with no nutrition goals set, I want to still get 3 relevant recipes based purely on my prompt, so that the feature is useful before I've configured a profile.
16. As a registered user with nutrition goals set, I want the results to be influenced by those goals in addition to my prompt text, so that "something high fiber" is grounded in my actual fiber target, not just the words "high fiber."
17. As a registered user, I want to always receive 3 results even for a narrow or unusual prompt, so that the experience is predictable even when the corpus is small.
18. As a registered user, if my query fails (e.g. transient API error) after retries are exhausted, I want to see an error state, so that I know to try again rather than waiting indefinitely.
19. As a site operator, I want a management command to ingest an initial batch of recipes from the source dataset, so that I can seed the corpus without processing the entire 39k-row dataset.
20. As a site operator, I want the ingestion command to curate the batch (dedupe by recipe name, spread across meal/diet types) rather than take a naive slice, so that the seeded corpus is diverse enough to produce good demo results.
21. As a site operator, I want the ingestion command to compute per-serving nutrition values and generate embeddings for each ingested recipe, so that recipes are immediately usable for retrieval after ingestion.
22. As a site operator, I want the ingestion command to be re-runnable with a different row limit, so that I can grow the corpus later without a schema change.
23. As a developer, I want the query-processing pipeline to run asynchronously via a background worker rather than blocking the web request, so that slow embedding/LLM calls don't risk web request timeouts.
24. As a developer, I want transient failures calling the embedding or generation APIs to be retried automatically before being surfaced as an error, so that normal API flakiness doesn't degrade the user experience.

## Implementation Decisions

**Stack**: Django web app, Postgres with the `pgvector` extension, Redis as the Celery broker/result backend, a Celery worker process, Docker Compose for local orchestration. Voyage AI (`voyage-3-lite`) for embeddings. Anthropic Claude Haiku 4.5 for the final recipe selection/description step.

**Data models**
- `Profile`: one-to-one with Django's built-in `User`. Holds optional numeric nutrition goal fields: daily calorie target, protein target, carbs target, fat target, fiber target.
- `Recipe`: seeded via ingestion, not user-editable. Fields:
  - Raw/display fields carried over from the source dataset: recipe name, source URL, image URL, servings, ingredient lines (plain text), diet labels, health labels, cautions, cuisine type, meal type, dish type.
  - Flattened per-serving nutrition columns computed at ingest time (source values are whole-recipe totals, divided by `servings`): calories, protein, carbs, fat, fiber, sugar, sodium.
  - An embedding vector (`pgvector`) computed from a composed text string: recipe name + ingredient lines + diet/health labels + meal/dish type + a generated nutrition-summary sentence.
  - Fields explicitly dropped from the source dataset as redundant: `daily_values`, `digest`, and the structured (dict-based) `ingredients` field — `ingredient_lines` covers the display/embedding need for ingredients.
- `QueryRequest`: user FK, prompt text, status enum (`pending` / `running` / `done` / `error`), result data (the 3 selected recipes + generated descriptions), timestamps. Drives both the polling UI and (unsurfaced for now) a full history of past queries per user.

**Ingestion (management command)**
- A management command accepts a row limit (default 100) and pulls from the source dataset (`datahiveai/recipes-with-nutrition`).
- Selection is curated, not a naive slice: dedupe by `recipe_name`, aim for spread across `meal_type`/`dish_type`/`diet_labels`, skip rows with broken/missing critical fields.
- For each selected row: parse the JSON-string fields (`total_nutrients`, label arrays), flatten per-serving nutrition values, compose the embedding input text, call Voyage AI to generate the embedding, and persist a `Recipe`.

**Query flow**
1. User (must be authenticated) submits a prompt via a Django view, which creates a `QueryRequest` (status `pending`) and enqueues a Celery task.
2. UI shows a loading state and polls a status endpoint until the `QueryRequest` reaches `done` or `error`.
3. Celery task (status → `running`):
   a. Embeds the prompt text via Voyage AI.
   b. Retrieves the top 15 candidate recipes by `pgvector` cosine similarity against the prompt embedding.
   c. If the user's `Profile` has any nutrition goals set, re-ranks/scores those 15 candidates by closeness to the goal values on the flattened per-serving nutrition columns, and narrows to the top 5. If no goals are set, skips straight to the top 5 by similarity.
   d. Sends the top 5 candidates (with their nutrition data) plus the original prompt to Claude Haiku 4.5, which selects and writes short descriptions for the final 3.
   e. Persists the 3 results onto the `QueryRequest` and sets status `done`.
4. On a transient failure calling Voyage or Claude, the task auto-retries (Celery autoretry, ~2–3 attempts with exponential backoff) before setting status `error`.
5. The result always contains exactly 3 recipes — no partial-result UI for sparse matches at this corpus size.

**Frontend**: Django server-rendered templates with light JS/HTMX for the submit → poll → render loop. No SPA framework.

**Auth**: Django's built-in `User`/session auth. Query submission requires login.

**Result display fields per recipe**: description (Claude-generated), per-serving nutrition stats (calories/protein/carbs/fat/fiber/sugar/sodium), source link, image (when present).

## Testing Decisions

Tests should exercise external behavior (HTTP requests/responses and command invocations) rather than internal implementation details of the retrieval/ranking logic, per this project's testing approach established during design.

Two seams, agreed with the developer:

1. **Query flow seam (primary)** — Django test client driving the submit-query and poll-status endpoints, with Celery configured to run tasks eagerly (`CELERY_TASK_ALWAYS_EAGER`) so the full pipeline (embed → retrieve → goal-based re-rank → generate) executes synchronously within the test. The Voyage and Claude HTTP clients are stubbed at their boundary so tests are deterministic, free, and don't require network access. Cases to cover: goals set vs. not set (verifies the re-rank branch is/isn't applied), always-3-results behavior, and the retry-then-error path when the stubbed client is made to fail repeatedly.
2. **Ingestion seam** — the ingestion management command invoked via `call_command`, with the Voyage client stubbed the same way. Cases to cover: dedupe/curation behavior on a sample input, correct per-serving flattening math, and re-run with a different limit.

No prior art exists in this codebase yet (greenfield project) — these two seams establish the pattern for future tests in this area.

## Out of Scope

- Query history UI (the `QueryRequest` model persists everything needed, but no "past queries" list is built now).
- Dietary restrictions / allergy filtering as a first-class goal input (health/caution labels are stored on `Recipe` for future use, but not yet surfaced as user-settable filters).
- Anonymous/guest query submission.
- Growing the corpus beyond the initial curated batch, or re-embedding on dataset updates.
- Rate limiting or per-user cost controls on API usage.
- Variable-count results (fewer than 3) for sparse-match queries.
- Any UI beyond the profile/goals form and the submit → loading → 3-results flow (no recipe browsing, search history, favorites, etc.).
- Deployment/production infrastructure — scope is local Docker Compose only.

## Further Notes

- Source dataset: `hf://datasets/datahiveai/recipes-with-nutrition/recipes-with-nutrition.csv` — 39,447 rows, 18 columns. Only `calories` exists as a flat numeric column in the source; all other nutrients live inside a `total_nutrients` JSON blob keyed by USDA/Edamam tags (`PROCNT`=protein, `FAT`, `CHOCDF`=carbs, `FIBTG`=fiber, `SUGAR`, `NA`=sodium, etc.), and all nutrient totals in the source (including `calories`) are whole-recipe totals, not per-serving.
- Data quality notes from the source dataset worth remembering during ingestion implementation: ~0.7% null `image_url`, 1,205 duplicate `recipe_name` values, and inconsistent formatting conventions in `ingredient_lines` across the several scraped sources represented (Food Network, food.com, Allrecipes, Food52, etc.).
- No issue tracker was configured for this project at spec time, so this spec is delivered as a file in `specs/` rather than published to a tracker. If a tracker is set up later (via `/setup-matt-pocock-skills`), this file can be republished there with the `ready-for-agent` label.
