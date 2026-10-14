# Implementation Plan: Decline Off-Topic Requests

**Feature Directory**: `specs/002-off-topic-requests` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

## Summary

The interpreter call that already runs first in every AI search also returns
`on_topic`. When it is false, the resolver stops right there: no embedding,
search, check or pick. The request finishes as `done` with no results and
`off_topic: true`, and the page shows a friendly message.

## Technical Context

Unchanged from 001 (Django 5.1 + DRF, Celery, Pydantic AI 2.54, Postgres + pgvector, Next.js). One new boolean column. Scale: tens of concurrent requests.

## Constitution Check

| Article | Status | Evidence |
|---------|--------|----------|
| I. Durable Design | Pass | One decision inside the existing interpreter seam; no new call or service. |
| II. Ports and Adapters | Pass | `RequestInterpreter` port unchanged in shape; fake gains one constructor argument. |
| III. Deep Modules | Pass | `Resolver.resolve` stays the one entry point; "Off-topic request" added to CONTEXT.md. |
| IV. Scalability | Pass | Saves the search and the second AI call for off-topic requests; expand-only migration with a DB default. |
| V. Security by Default | Pass | Owner-scoped poll unchanged; the field is validated by Pydantic; prompt text not logged. |
| VI. Focused Testing | Pass | One unit test of the early stop; no E2E or HTTP-level tests. |
| VII. Observability | Pass | `query_declined_off_topic` log with `query_request_id`. |
| VIII. Least New Code | Pass | No judge call, no keyword list, no new status or reason enum. |

## Design

- `Interpretation.on_topic: bool = True`. The default means a missing field fails open (FR-005).
- Interpreter instructions: one sentence, lenient (FR-002).
- `Resolution.off_topic: bool = False`. `Resolver.resolve` returns `Resolution([], [], off_topic=True)` right after interpreting (FR-003).
- `QueryRequest.off_topic` (`BooleanField`, `db_default=False`, migration 0005), stored by `succeed(results, unmet_targets, off_topic=False)`.
- Task passes it through and logs `query_declined_off_topic`.
- API (additive): `QueryOut.off_topic: bool`; `results` is `[]` when declined.
- Frontend: the results view shows the message in place of cards, not the error alert (FR-004).

**Rejected**: a separate LLM-judge call (adds a call and latency to every on-topic request), keyword lists (brittle), a similarity threshold (hard to tune, rejects vague food requests), a new `declined` status (the lifecycle and polling depend on the current four).

## Testing Strategy

- `queries/tests/test_resolution.py`: an off-topic interpretation reports only the understanding step, never calls the picker, and returns no results with `off_topic=True`.

Eval (constitution 2.1.0): `manage.py eval_interpreter` runs 10 off-topic and 20 food prompts against the real model and fails below SC-003. On demand, not in the unit suite.

Not tested: serializer, migration, frontend message (type-check, lint, quickstart).

## Requirement Coverage

| Requirement | Where |
|-------------|-------|
| FR-001, FR-002, FR-005 | `Interpretation.on_topic`, interpreter instructions |
| FR-003 | early return in `Resolver.resolve` |
| FR-004 | `search-panel.tsx` results view; `succeed` (done, not error) |
| FR-006 | unchanged owner filter in `QueryStatusView` |
| SC-001, SC-002 | no new calls; early return skips the picker |
| SC-003 | `eval_interpreter` command |
