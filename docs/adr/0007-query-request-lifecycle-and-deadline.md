# 0007 — Query request lifecycle owned by the model, with a server-side deadline

Date: 2026-10-08 · Status: accepted · Builds on 0005

## Context

The query request lifecycle (`pending → running → done | error`) was spread across four places:
- **"Finished" was defined twice:** in `queries/api.py` and in `queries/tasks.py`.
- **Status changes were plain field assignments** in the task. Each one overwrote the row, so the last write won.
- **`elapsed_seconds` was `updated_at - created_at`,** so it changed whenever anything saved a finished row, such as an admin edit.
- **Nothing on the server ended a request whose worker died** or never picked it up; it stayed `pending` or `running` forever. The dev database had a request stuck in `running` since August. The frontend's hard-coded 150 s, copied from the retry settings, was the only time limit.

Fixing reload (resuming a search from its id in the URL) needs the server to own that time limit. Otherwise a reloaded page could poll forever for a request that no worker will ever finish.

## Decision

- **`QueryRequest` owns its lifecycle.** The only way to change `status` is through these methods:
  - `start()`, `succeed(results)`, `fail(message)`;
  - `expire_if_overdue()`, plus `is_finished`, `deadline` and `elapsed_seconds`.
- **Every transition is a conditional update** (`UPDATE … WHERE status IN (pending, running)`), and it returns whether it took effect. A late attempt or a duplicate delivery can't overwrite a finished request. This closes ADR 0005's "can resolve twice, last write wins" note for finished requests.
- **Every request gets a deadline when it is submitted:** `expires_at = now + QUERY_DEADLINE_SECONDS`, default 150. Stamping it per request means a config change doesn't move the deadline of requests already in flight.
  - Startup (`QueriesConfig.ready`) rejects a deadline shorter than the worst case of the retry policy (`worst_case_seconds()`: every attempt timing out, plus every backoff at its ceiling; 134 s today).
- **Past its deadline, a request can only end as an error.** Expiry is checked whenever someone looks, with no sweeper:
  - **The poll endpoint** expires an overdue request before answering.
  - **The worker** expires it instead of starting, and `succeed` expires it instead of storing late results.
  - **A retry that would start after the deadline isn't queued;** the request fails at once, with `deadline_reached` in the log.
  - **An expired request's `finished_at` is its deadline,** not the moment someone happened to notice. Its `elapsed_seconds` is therefore the full wait the user was promised.
- **`finished_at` is stored,** and `elapsed_seconds = finished_at - created_at`.
- **The poll response adds `created_at` and `expires_at`.** The frontend no longer has a deadline of its own: it polls until `done` or `error`. Its only safety net is the server's own budget (`expires_at - created_at`, so a skewed client clock doesn't matter) plus 30 s of grace.

## Consequences

- **Overdue rows nobody polls stay `pending` or `running` in the database** until something reads them. That's harmless, because every reader expires them first. A periodic sweep (Celery beat) can be added if reporting needs a tidy table.
- **Migrations follow expand → migrate:**
  - `0002` adds nullable `expires_at` and `finished_at`. The column is added without a default first, so existing rows aren't all stamped with the same "now + deadline".
  - `0003` backfills `expires_at = created_at + 150 s`, and `finished_at = updated_at` for finished rows.
  - The contract step, making both NOT NULL, is a `TODO(contract)` in `queries/models.py`. Until then, a row with no `expires_at` falls back to `created_at + QUERY_DEADLINE_SECONDS`.
- **The admin shows lifecycle fields as read-only,** so status can't be edited by hand.
- **New log event:** `query_expired` (WARNING) when an attempt finds its request already expired.
- **E2E:** the existing AI search journey covers the new response fields. A browser test for "a dead worker ends in an error" needs reload/resume (the next candidate); until then the API tests cover it.
