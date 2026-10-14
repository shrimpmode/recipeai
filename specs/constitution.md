# Nutrition (RecipeAI) Constitution

## Core Principles

### I. Durable Design

Build for the system as it will be when the codebase and traffic triple.
When an option is cheap now but costly later, choose the durable one and
record the trade-off. Durable means structurally sound, not gold-plated:
YAGNI applies to features, never to structure.

### II. Ports and Adapters

Domain logic MUST be pure and free of I/O. HTTP, databases, queues, and
third-party APIs (LLM providers, the embedding model) live in adapters at
the edges. Dependencies point inward and are injected through constructors
or parameters; settings choose adapters (`AI_SEARCH_*`), tests swap in the
fakes from `queries/tests/fakes.py`. Nothing is patched by import path.

### III. Deep Modules and Named Patterns

Modules expose small interfaces over substantial behaviour, with decisions
likely to change behind a seam. A pattern (strategy, repository, adapter,
factory, …) is used only when it resolves a real force, and the plan names
it. Prefer composition and immutable data; make illegal states
unrepresentable with precise types validated at the boundary. Domain terms
follow `CONTEXT.md`; a new term is added there.

### IV. Scalability

Web processes MUST be stateless; slow or failure-prone work (embedding, LLM
calls) runs on the Celery worker, never in a web request. Every query is
checked for indexes and N+1 access; lists are paginated. Retries live in one
layer (the Celery task) with exponential backoff and jitter. Every network
call has a timeout, and every AI search finishes by its deadline (ADR 0007).
Schema changes are backward compatible (expand → migrate → contract).

### V. Security by Default

Input is validated at every trust boundary. Every entry point declares who
may call it and enforces authorization server-side (a user sees only their
own query requests). Secrets come from the environment, never the code.
Provider error text never reaches the API. Every feature passes an OWASP
check before it ships; Critical and High findings block release.

### VI. Focused Testing

Unit tests cover domain rules, security decisions, parsers and
calculations, and every bug fix (as a regression test), written before the
code. Framework wiring, configuration, thin adapters, and plain data
classes are not unit-tested. Tests call domain and service code directly
(the real test database is allowed); there are no end-to-end, HTTP-level or
fake-provider-server tests.

### VII. Observability and Errors

Structured logs (`key=value`, `config/logging.py`) carry the request's
correlation ID (`query_request_id`). Errors are explicit and typed
(`PermanentFailure`, `UnusablePicks`, …), classified where they happen and
handled at the layer that can act on them. Configuration is typed and
validated at startup (`QueriesConfig.ready`).

### VIII. Least New Code

Write only what the requirements need, and reuse before writing: existing
code in this repo, then the standard library or platform, then an installed
dependency, and only then new code. No dependency for a few lines, no
options or config nobody asked for, no "for later" code. A change is
complete only when every caller, test, and fixture it affects is updated.
A deliberate shortcut carries `TODO(<limit>; upgrade when <trigger>)`.
This never removes structure, validation, error handling that prevents data
loss, security, or accessibility.

## Technology Constraints

Backend: Python 3, Django 5 + Django REST Framework, Postgres with pgvector,
Celery on Redis, Pydantic AI for LLM calls (provider chosen by
`AI_SEARCH_MODEL`), local sentence-transformers embeddings; uv, ruff,
pyright/mypy, pytest. Frontend: Next.js (App Router) + TypeScript, typed API
client generated from the OpenAPI schema (`pnpm gen:api`), eslint.
Docker Compose for local runs. Significant decisions are ADRs in
`docs/adr/`.

## Quality Gates

A feature is done when its unit tests, type check, lint, and formatting
pass; analyze reports no CRITICAL findings; converge reports Converged; and
the OWASP check has no open Critical or High findings. Trade-offs and
stopgaps are written in plan.md, an ADR, or a
`TODO(<limit>; upgrade when <trigger>)` in code.

## Governance

This constitution supersedes conflicting practices. Every plan runs the
Constitution Check; a violation needs a justification in Complexity
Tracking. Amendments state their rationale and bump the version (MAJOR:
principle removed or redefined, MINOR: principle added or expanded,
PATCH: wording).

**Version**: 2.0.0 | **Ratified**: 2026-10-13 | **Last Amended**: 2026-10-13

Amendment 2.0.0: Article VI redefined. End-to-end (Playwright) and
HTTP-level/integration tests were removed from the repo at the owner's
request; tests now target domain and service code only.
