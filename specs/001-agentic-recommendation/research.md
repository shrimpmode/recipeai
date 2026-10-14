# Research: Goal-Checked Recommendations

## R1. Orchestration: plain loop vs. pydantic-graph vs. tool-calling agent

- **Decision**: a plain function (`Resolver.resolve`) with a fixed step order; Pydantic AI agents only at the two AI steps.
- **Rationale**: the flow is a straight line with one small loop over search levels; Celery already re-runs a failed attempt. A fixed order keeps AI cost, timing and progress labels predictable (spec clarification 2).
- **Alternatives**: `pydantic-graph` (ships with Pydantic AI 2.54): earns its place for branching, user pauses or resume-from-state; adopt when the flow needs one of those. A tool-calling agent: variable loops and cost, harder to bound by the deadline.

## R2. Filtered vector search

- **Decision**: nutrient limits as a SQL `WHERE` on per-serving columns, `ORDER BY` cosine distance, `LIMIT RETRIEVAL_CANDIDATE_COUNT`; then rank in Python by targets met, then distance to target.
- **Rationale**: with a selective filter, Postgres can scan the filtered rows exactly (~39k rows at most); with a broad filter it uses the HNSW index and post-filters. pgvector ≥ 0.8 (shipped in `pgvector/pgvector:pg16`) can keep scanning the index until the limit is met (`hnsw.iterative_scan`), which fixes short results when the planner picks HNSW.
- **Applied (review fix)**: each search runs `SET LOCAL hnsw.iterative_scan = strict_order` in its own transaction, so a selective filter still returns `limit` rows.
- **Alternatives**: retrieving top-N by similarity then checking (the old design) misses goal-meeting recipes beyond N; B-tree indexes per nutrient column: not needed at this size.

## R3. Progress transport

- **Decision**: `progress` JSON list on `QueryRequest`, written by the worker per step, returned by the existing poll.
- **Alternatives**: SSE/WebSockets need async views or a channel layer; Redis pub/sub adds a second source of truth.

## R4. Deadline budget

- **Decision**: `AI_SEARCH_MODEL_TIMEOUT_SECONDS` default 30 → 15; `worst_case_seconds()` multiplies by `AI_CALLS_PER_ATTEMPT = 2`: 4 × 2 × 15 + 14 = 134 s ≤ 150 s.
- **Alternatives**: fewer retries (fails sooner on flaky providers); a longer deadline (longer worst-case wait for users).
