# Tasks: Decline Off-Topic Requests

**Input**: `specs/002-off-topic-requests/` — plan.md, spec.md

**Format**: `- [ ] T### [P] [US#] Description with exact file path`

## Phase 1: User Story 1 - Decline clearly off-topic requests (P1) MVP

**Goal**: off-topic requests end after understanding with a friendly message.
**Independent Test**: spec US1.

- [X] T001 [US1] Unit test: off-topic interpretation → steps `[understanding]`, no picker call, `results == []`, `off_topic` true, in queries/tests/test_resolution.py — must fail first
- [X] T002 [US1] `FakeInterpreter(on_topic=True)` constructor argument in queries/tests/fakes.py
- [X] T003 [US1] `Interpretation.on_topic` (default `True`), `Resolution.off_topic`, early return in queries/services/resolution.py
- [X] T004 [US1] Lenient on-topic sentence in the interpreter instructions in queries/services/generation.py
- [X] T005 [US1] `off_topic` BooleanField (`db_default=False`) and `succeed(..., off_topic=False)` in queries/models.py; queries/migrations/0005_query_request_off_topic.py
- [X] T006 [US1] Pass `off_topic` and log `query_declined_off_topic` in queries/tasks.py
- [X] T007 [US1] `off_topic` on `QueryOut` in queries/api.py; `pnpm gen:api`
- [X] T008 [US1] Friendly message in place of cards in frontend/src/components/search/search-panel.tsx

**Checkpoint**: unit suite, mypy, ruff, tsc, eslint green.

## Phase 2: Polish

- [X] T009 "Off-topic request" in CONTEXT.md; Understand and Poll steps in templates/docs/manual.html; supersede note in specs/001-agentic-recommendation/spec.md
- [X] T010 Review (incl. owasp-check) over the feature diff

## Phase 3: Convergence

- [X] T011 SC-003 measured by hand only (partial): `eval_interpreter` command in queries/management/commands/eval_interpreter.py; constitution 2.1.0 allows on-demand evals
