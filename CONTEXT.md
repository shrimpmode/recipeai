# Domain glossary

Terms used in code, ADRs and reviews. Keep them consistent.

- **Recipe**: one dish from the source corpus, with per-serving nutrition and, once backfilled, an embedding (`recipes.models.Recipe`).
- **Goals**: a user's optional daily nutrition targets (calories, protein, carbs, fat, fiber), stored on `Profile`. Scoring uses one meal's share of each: a third of the daily target.
- **AI search**: a free-text prompt resolved in the background into exactly `RESULT_COUNT` (3) described recipes. Submitted as a **query request**, then polled.
- **Query request**: one AI search and its lifecycle: `pending → running → done | error` (`queries.models.QueryRequest`). Only its transition methods change the status, and a finished request is never overwritten (ADR 0007).
- **Deadline**: when a query request must have finished (`expires_at`, stamped at submit from `QUERY_DEADLINE_SECONDS`). Past it, the request can only end as an error; whoever looks first (the poll or the worker) expires it.
- **AI search resolution**: the module that turns a prompt and goals into results (`queries/services/resolution.py`, `Resolver`). It embeds the prompt, builds the shortlist and asks the picker.
- **Shortlist**: the recipes the picker chooses from: the nearest by vector similarity, re-ranked by goals when the user has any (`RETRIEVAL_RERANKED_COUNT`, 5).
- **Pick**: one recipe the picker chose from the shortlist, with a short description of why it fits.
- **Picker**: whatever chooses and describes the final recipes (`RecipePicker`). In production that is an LLM through Pydantic AI (`LLMPicker`).
- **Model spec**: the `provider:model` string naming the LLM behind the picker (`AI_SEARCH_MODEL`, e.g. `anthropic:claude-haiku-4-5-20251001`). Providers are registered in `queries/services/model_providers.py` (ADR 0006).
- **Permanent failure**: a failure that will repeat on retry (bad credentials, a request the model provider rejects, no API key configured). It ends a query request at once.
- **Keyword search**: synchronous search of recipe names and ingredients, without AI (`recipes/services/keyword_search.py`).
- **Corpus load / embedding backfill**: loading the recipe dataset, then embedding the recipes that need it, resumably (ADR 0001).
