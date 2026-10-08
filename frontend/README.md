# Frontend

Next.js 16 (App Router, TypeScript, Tailwind 4) UI for the Nutrition app. It talks to the Django API through a same-origin `/api` rewrite; see `docs/adr/0003-nextjs-frontend-django-api.md` and the repo README for running it.

- `src/app` — routes: `/login`, `/` (AI and keyword search), `/goals`
- `src/components` — UI; design tokens live in `src/app/globals.css` (flat palette; each token holds its light and dark value via `light-dark()`); `theme-toggle.tsx` switches System / Light / Dark
- `src/lib/api` — typed API client; `schema.d.ts` is generated (`pnpm gen:api`), don't edit it
- `src/proxy.ts` — redirects visitors without a session to `/login`
- `e2e` — Playwright tests against the full stack, Claude stubbed
