# Implementation Plan: Goal-Checked Recommendations with Live Progress

**Feature Directory**: `specs/001-agentic-recommendation` | **Date**: 2026-10-13 | **Spec**: [spec.md](spec.md)

## Summary

An AI search becomes a fixed, five-step flow inside the existing Celery task:
an AI interpreter turns the prompt into a search phrase and nutrient intents;
pure code merges them with the user's goals into nutrition targets; the
search filters the whole corpus by those targets in SQL and ranks by vector
similarity, widening in a fixed order when fewer than a shortlist match; pure
code checks each candidate; the existing AI picker chooses and describes 3.
Each step is recorded on the query request and returned by the existing
1-second poll, which the page renders as a progress list.

## Technical Context

**Language/Version**: Python 3.12, TypeScript 5 (Next.js App Router)
**Primary Dependencies**: Django 5.1 + DRF, Celery, Pydantic AI 2.54 (already installed), pgvector
**Storage**: Postgres 16 + pgvector (`pgvector/pgvector:pg16`); two new JSON columns on `queries_queryrequest`
**Unit Test Framework**: Django `TestCase` via `manage.py test` (real Postgres)
**Target Platform**: Docker Compose (web, worker, db, redis, frontend)
**Performance Goals**: SC-002 first step visible < 2 s; SC-003 p95 < 15 s
**Constraints**: every request finishes by its 150 s deadline (ADR 0007); at most 2 AI calls per attempt (SC-005)
**Scale**: ~39k recipes, tens of concurrent requests; corpus may triple

## Constitution Check

| Article | Status | Evidence / Justification |
|---------|--------|--------------------------|
| I. Durable Design | Pass | Targets and widening are a pure module; the flow is one function; graph library deferred with a stated trigger. |
| II. Ports and Adapters | Pass | New `RequestInterpreter` port; LLM adapter + fake chosen by `AI_SEARCH_INTERPRETER`; no import-path patching. |
| III. Deep Modules and Named Patterns | Pass | `Resolver.resolve` stays the one entry point; enums for nutrient/direction/step; new terms in CONTEXT.md. |
| IV. Scalability | Pass | Work stays on the worker; filtered search uses existing indexes (see research R2); deadline re-checked at startup with calls-per-attempt. |
| V. Security by Default | Pass | Same owner-only endpoints; step codes, not text, cross the API; intents validated by Pydantic before use. |
| VI. Focused Testing | Pass | Unit tests only for targets/check/widening and the flow's search behaviour; user asked to test only critical parts. No E2E or HTTP-level tests (constitution 2.0.0). |
| VII. Observability and Errors | Pass | Interpreter errors classified like the picker's; `query_request_id` on logs; no prompt or goals logged. |
| VIII. Least New Code | Pass | Reuses poll, task, retries, `build_model`, picker; no SSE, no graph library, no AI refinement. |

## Architecture

**Patterns**:

| Pattern | Where | Force it resolves |
|---------|-------|-------------------|
| Adapter (behind a port) | `RequestInterpreter` → `LLMInterpreter` / `FakeInterpreter` | Swap the model provider; test without a model |
| Strategy (as data) | `widening_levels()` returns ordered `SearchLevel`s | The widening order is a list, not branching code |
| Value object | `NutritionTarget`, `NutrientIntent` | Validated at the boundary; illegal directions unrepresentable |

**Domain vs. adapters**: `queries/services/targets.py` is pure (no Django, no I/O): merge, tolerances, check, ranking, widening. `queries/services/resolution.py` orchestrates and owns the ports. `queries/services/retrieval.py` turns a `SearchLevel` into one SQL query. `queries/services/generation.py` holds both LLM adapters with shared error classification. `queries/tasks.py` wires the progress reporter to the model.

**Scalability**: one SQL query per search level (≤ 4); nutrient filters on numeric columns + `ORDER BY` cosine distance, `LIMIT RETRIEVAL_CANDIDATE_COUNT`. Progress writes are one conditional `UPDATE` per step (≤ 6 per attempt). Migration is additive with DB defaults, safe for old processes.

**Reused**: poll endpoint and `SearchPanel` loop, `QueryRequest` transitions, Celery retries and deadline, `build_model`, `LLMPicker`, fakes pattern, `_candidate` / `_result` shapes.

**Not built**: AI rephrasing of the search, SSE/WebSockets, `pydantic-graph`, progress after reload, interpretation caching across retries.

**Trade-offs**:
- Model timeout 30 s → 15 s so 2 calls × 4 attempts + backoff = 134 s still fits 150 s. Cost: a very slow provider answer fails sooner.
- A retry re-runs the interpret call (one cheap call) rather than storing interim state.
- Goals are re-read on a retry, so an edit between attempts is picked up. Accepted: retries are rare and seconds apart.

## Security Design

| Entry point | Caller | AuthN / AuthZ | Untrusted input | Sensitive data |
|-------------|--------|---------------|-----------------|----------------|
| `POST /api/queries` | signed-in user | session + CSRF; creates own request | `prompt` (≤ 1000 chars) | prompt |
| `GET /api/queries/{id}` | signed-in user | session; `user=request.user` filter (404 otherwise) | path id | goals-derived checks, results |
| LLM answer (interpreter) | model provider | n/a | whole output: validated by Pydantic (enums, amount > 0) | prompt sent to provider |

## Testing Strategy

Critical units only (per the user's instruction):

- Target merging, met thresholds, missing values, widening order → `queries/tests/test_targets.py`
- The flow: a goal-meeting recipe wins over a closer one that misses, widening is reported, unmet targets named → `queries/tests/test_resolution.py`
- Progress can't be written to a finished request and is cleared on a retry → `queries/tests/test_lifecycle.py`

Not tested: the LLM interpreter adapter (thin, mirrors `LLMPicker`), serializers, API views, frontend components; covered by type-check, lint and quickstart.md.

## Project Structure

```text
queries/services/targets.py          new: pure targets, check, widening
queries/services/resolution.py       flow, Step enum, RequestInterpreter port, Resolution
queries/services/retrieval.py        search_level() replaces select_candidates/rerank_by_goals
queries/services/generation.py       LLMInterpreter; shared agent runner; picker sees goal checks
queries/models.py + migrations/0004  progress, unmet_targets, report_step()
queries/tasks.py, queries/apps.py    reporter wiring; worst case × AI calls per attempt
queries/api.py                       progress, unmet_targets, goal_checks
config/settings.py                   AI_SEARCH_INTERPRETER; timeout 15 s
queries/tests/fakes.py               FakeInterpreter
frontend/src/components/search/      progress-steps.tsx; search-panel.tsx
frontend/src/components/recipe-card.tsx   goal checks
docs/adr/0008-*.md, CONTEXT.md
```

## Requirement Coverage

| Requirement | Plan section |
|-------------|--------------|
| FR-001, FR-001a | Summary; `resolution.py` flow |
| FR-002, FR-002a | `targets.py` merge and check |
| FR-003, FR-004 | `retrieval.search_level`, `widening_levels` |
| FR-005 | picker sees goal checks; `unmet_targets` |
| FR-006 | single unfiltered level when no targets |
| FR-007, FR-008 | `report_step`, `progress`, `ProgressSteps` labels |
| FR-009 | timeout 15 s; `worst_case_seconds` × 2 |
| FR-010 | unchanged picker validation |
| FR-011 | unchanged owner filter |
| FR-012 | no prompt/goal fields in new logs |
| SC-001 | manual sample run (quickstart) |
| SC-002, SC-003 | progress written at step start; quickstart timing |
| SC-004 | `goal_checks` on every result when targets exist |
| SC-005 | 2 AI calls per attempt by construction |
