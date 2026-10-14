# Tasks: Goal-Checked Recommendations with Live Progress

**Input**: `specs/001-agentic-recommendation/` — plan.md, spec.md, data-model.md, contracts/

**Format**: `- [ ] T### [P] [US#] Description with exact file path`

## Phase 1: Foundational

- [X] T001 Add `AI_SEARCH_INTERPRETER = "queries.services.generation.LLMInterpreter"` and default `AI_SEARCH_MODEL_TIMEOUT_SECONDS` 15 in config/settings.py
- [X] T002 Check `AI_SEARCH_INTERPRETER` at startup in queries/apps.py; `worst_case_seconds()` × `AI_CALLS_PER_ATTEMPT` (2) in queries/tasks.py
- [X] T003 Add `progress` and `unmet_targets` (JSON lists, `db_default` `[]`) plus `report_step()`; `start()` clears progress; `succeed(results, unmet_targets)` in queries/models.py and queries/migrations/0004_query_request_progress.py

**Checkpoint**: migrations apply; existing suite green.

## Phase 2: User Story 1 - Recommendations checked against my goals (P1) MVP

**Goal**: targets narrow the search; widening in fixed order; each result carries goal checks; unmet targets named.
**Independent Test**: spec US1.

- [X] T004 [US1] Unit tests: request beats goal, stated/reference amounts, minimum vs band thresholds, missing value never met, widening order, in queries/tests/test_targets.py — must fail first
- [X] T005 [US1] Pure targets module (`Nutrient`, `Direction`, `NutrientIntent` with `amount > 0`, `NutritionTarget`, `merge_targets`, `is_met`, `check`, `rank_key`, `SearchLevel`, `widening_levels`) in queries/services/targets.py
- [X] T006 [US1] Unit tests: a goal-meeting recipe beats a closer one that misses; widening reported once and in order; unmet targets named; no targets → no check step, in queries/tests/test_resolution.py — must fail first
- [X] T007 [US1] `search_level()` (SQL limits + similarity, ranked by targets met) replacing `select_candidates`/`rerank_by_goals` in queries/services/retrieval.py
- [X] T008 [US1] `RequestInterpreter` port, `Interpretation`, `Step`, `Resolution`, the fixed flow with a `report` callback in queries/services/resolution.py
- [X] T009 [US1] `LLMInterpreter` adapter sharing the picker's error classification; picker instructions mention goal checks in queries/services/generation.py
- [X] T010 [US1] `FakeInterpreter` and settings override in queries/tests/fakes.py; update existing callers in queries/tests/test_resolution.py, queries/tests/test_query_flow.py
- [X] T011 [US1] Task passes the reporter and stores `unmet_targets` in queries/tasks.py
- [X] T012 [US1] API: `goal_checks` on `ResultOut` (default `[]`), `unmet_targets` on `QueryOut` in queries/api.py
- [X] T013 [US1] E2E stub answers the interpreter call in frontend/e2e/claude-stub/server.mjs
- [X] T014 [US1] Regenerate API types (`pnpm gen:api`); goal checks and unmet note on frontend/src/components/recipe-card.tsx and frontend/src/components/search/search-panel.tsx

**Checkpoint**: unit suite, mypy, ruff, tsc, eslint green.

## Phase 3: User Story 2 - Live progress (P2)

- [X] T015 [US2] Unit test: `report_step` refuses a finished request; `start()` clears progress, in queries/tests/test_lifecycle.py — must fail first
- [X] T016 [US2] `progress` on `QueryOut` in queries/api.py
- [X] T017 [US2] `ProgressSteps` list with plain labels in frontend/src/components/search/progress-steps.tsx; render it while searching in frontend/src/components/search/search-panel.tsx

**Checkpoint**: suite green; quickstart US2.

## Phase 4: Polish

- [X] T018 ADR docs/adr/0008-goal-checked-search-and-progress.md; terms in CONTEXT.md
- [X] T019 Review (incl. owasp-check) over the feature diff
