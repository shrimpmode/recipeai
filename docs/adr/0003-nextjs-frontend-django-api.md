# 0003 — Next.js frontend over a Django JSON API, one origin via rewrites

Date: 2026-10-07 · Status: accepted; API framework superseded by [0004](0004-django-rest-framework-api.md) (django-ninja → Django REST Framework)

## Context

The UI was Django templates + HTMX. We are moving it to Next.js for a richer, typed frontend while keeping Django as the owner of data, auth, the Celery pipeline and the admin.

## Decision

- **Django serves JSON under `/api/`**, built with django-ninja: typed request/response schemas (pydantic), validation errors as 422, and an OpenAPI document generated from the code. The HTMX views and templates are removed; admin and the staff manual (`/docs/`) stay on Django.
- **Typed contract.** `pnpm gen:api` exports the OpenAPI schema and generates `frontend/src/lib/api/schema.d.ts` (openapi-typescript); the frontend calls the API through openapi-fetch, so a renamed field is a TypeScript error, not a runtime surprise.
- **One origin.** The browser only talks to Next.js; `next.config.ts` rewrites `/api/*` to Django. Django's own `sessionid` and `csrftoken` cookies therefore work unchanged: no CORS, no tokens in JavaScript-readable storage. Unsafe requests send `X-CSRFToken`; `CSRF_TRUSTED_ORIGINS` (`FRONTEND_ORIGINS`) trusts the frontend's Origin header. Login is CSRF-checked explicitly (django-ninja skips unauthenticated endpoints).
- **Auth gating.** `src/proxy.ts` does an optimistic cookie-presence redirect to `/login`; Django is the authority (401), and the API client returns the user to `/login` on any 401.
- **Pages are static shells with client components** (Cache Components is on). Nothing reads cookies during server rendering, so every route prerenders and the session never blocks a page.
- **AI search keeps its async shape:** `POST /api/queries` returns 202, the client polls `GET /api/queries/{id}`. Provider error text is logged, never returned.

Rejected: calling Django directly from the browser (cross-origin cookies, CORS and CSRF configuration, SameSite constraints); token auth (JWT) — more surface for no gain while one frontend talks to one API; DRF — heavier for a small API and needs a separate OpenAPI layer.

## Consequences

- Two dev servers (Next on :3000, Django on :8000); `docker compose up` runs both.
- Rewrite destinations are fixed at `next build` time: production images need `BACKEND_URL` as a build argument.
- The API is now a contract: change it, then run `pnpm gen:api` and commit the regenerated schema. A CI check that the committed schema matches the code is a follow-up.
- E2E tests (Playwright) run against the full stack with only Claude stubbed (`docker-compose.e2e.yml`).
