# 0004 — Django REST Framework for the JSON API

Date: 2026-10-08 · Status: accepted · Supersedes the API-framework choice in [0003](0003-nextjs-frontend-django-api.md)

## Context

ADR 0003 built the JSON API on django-ninja and rejected DRF as heavier for a small API. We are standardising on Django REST Framework: it's the most widely used and longest-maintained Django API framework, and it comes with things this API will need as it grows — throttling (login has none today), pagination, permissions, and a large ecosystem.

## Decision

- **DRF serves `/api/`.** Each app's `api.py` holds its serializers and `APIView`s. `config/api.py` maps the URLs, without trailing slashes, so every path and response shape is unchanged for the frontend.
- **Defaults** (`REST_FRAMEWORK` in settings): JSON only; session auth; `IsAuthenticated` unless a view opts out (the `csrf` and `login` endpoints).
- **401 for anonymous requests.** `config.rest.SessionAuthentication` names a `WWW-Authenticate` scheme. Without one, DRF would answer anonymous requests with 403, and the frontend's redirect to `/login` relies on 401. A 403 still means a CSRF failure.
- **CSRF is unchanged on the wire.** DRF's session auth checks CSRF on unsafe requests from logged-in users. `login` checks it explicitly (`config.rest.enforce_csrf`) to block login CSRF.
- **OpenAPI comes from drf-spectacular.** `pnpm gen:api` runs `manage.py spectacular --validate --fail-on-warn`, so an endpoint the schema can't describe fails generation instead of yielding a loose type. Component names keep the old ones (`Me`, `Goals`, `QueryOut`, …). With `COMPONENT_SPLIT_REQUEST`, request bodies get their own `…Request` types. The schema and Swagger UI are served at `/api/schema` and `/api/docs` in DEBUG only.

## Consequences

- **Validation errors are 400, not 422**, with DRF's per-field error body. The frontend only checks `response.ok`, so it is unaffected.
- **Two new dependencies:** `djangorestframework` and `drf-spectacular`, plus `djangorestframework-stubs` for mypy. `django-ninja` and its pydantic dependency are gone.
- **Request schemas and response serializers are now classes instead of type annotations.** They're a little more verbose, but they validate in the same place.
- **Follow-up:** add DRF throttling to `login` (per IP and per username).
