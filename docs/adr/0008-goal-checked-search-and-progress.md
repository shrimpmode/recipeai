# 0008 — Goal-checked AI search: targets narrow the search, a fixed flow, progress through the poll

Date: 2026-10-13 · Status: accepted · Builds on 0005, 0006, 0007 · Spec: `specs/001-agentic-recommendation/`

## Context

AI search took the 15 recipes closest to the prompt's embedding, nudged them towards the user's goals, and asked the picker for 3. Nothing ensured the picks met the goals, so "something high fiber" could return three recipes well below the user's fiber target. While it ran, the page only showed a spinner.

## Decision

- **A fixed flow in `Resolver.resolve`, in code:** understand → search → (widen) → check → choose. The order is not the model's choice.
  - Only two steps call an LLM, both Pydantic AI agents with typed output behind ports: `LLMInterpreter` (search phrase + nutrient intents) and `LLMPicker`.
  - `AI_CALLS_PER_ATTEMPT = 2`, whether or not the search widens.
- **Nutrition targets** (`queries/services/targets.py`, pure) merge the user's goals with the nutrients the request names; the request wins for a nutrient both cover. Amounts are per meal (a third of the day). Protein and fiber are minimums, calories, carbs and fat are bands, a request's "low" is a maximum.
- **Targets narrow the search, similarity ranks within it.** Limits become a SQL `WHERE` on the per-serving columns across the whole corpus; what passes is ordered by cosine distance.
- **Widening is a fixed list of search levels, not AI rephrasing:** strict → goals loosened (tolerance 0.2 → 0.4) → goals no longer limits → no limits. Each level's recipes are pooled and ranked by the request's own nutrients met, then targets met, then shortfall, so widening never loses a better recipe (ranking amended 2026-10-14: request nutrients first). The last level never filters, so the loop always ends.
- **Progress through the existing poll.** The worker records each step's code on `QueryRequest.progress` (`report_step`, a conditional update while running; `start()` clears it on a retry). The page maps codes to labels.
- **Results carry `goal_checks`; the request carries `unmet_targets`.** Additive API fields.
- **Model timeout 30 s → 15 s,** and `worst_case_seconds()` multiplies by calls per attempt: 4 attempts × 2 × 15 + 14 = 134 s, within the 150 s deadline. Retry count unchanged.

## Alternatives rejected

- **Check after a similarity search, refine with AI** (the first draft): misses goal-meeting recipes outside the nearest N, and costs up to 4 AI calls.
- **One agent with tools deciding the order:** variable cost and duration, harder to bound by the deadline and to report honestly.
- **`pydantic-graph`:** worth it for branching, pauses for the user, or resuming mid-run; this flow is a straight line. Revisit when one of those arrives.
- **SSE/WebSockets for progress:** need async views or a channel layer; the 1 s poll already meets the requirement.

## Consequences

- A filtered query on the HNSW index would only filter its first ~40 neighbours, so each search sets `hnsw.iterative_scan = strict_order` (pgvector ≥ 0.8; the image has 0.8.6) to keep scanning until enough rows pass.
- A retry re-runs the interpreter call too; goals are re-read on each attempt.
- Migration `0004` adds `progress` and `unmet_targets` with DB defaults, so processes on the old code keep inserting rows.
- Results stored before this change have no `goal_checks`; the API serves them as `[]`.
