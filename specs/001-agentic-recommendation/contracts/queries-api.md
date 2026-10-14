# Contract: AI search API (additive changes)

Auth unchanged: session + CSRF; a user only sees their own query requests (404 otherwise).

## `GET /api/queries/{id}` and `POST /api/queries` → `QueryOut`

```jsonc
{
  "id": 42,
  "status": "running",                       // pending | running | done | error
  "progress": ["understanding", "searching"], // new: step codes in order; [] when pending
  "unmet_targets": [],                        // new: nutrients none of the results meet (done only)
  "results": null,                            // done: 3 × ResultOut
  "elapsed_seconds": null,
  "created_at": "…",
  "expires_at": "…"
}
```

`ResultOut` gains:

```jsonc
"goal_checks": [
  { "nutrient": "fiber", "direction": "at_least", "target": 9.3, "value": 11.2, "met": true }
]
```

Errors unchanged: 400 for a blank or > 1000-char prompt, 401 signed out, 404 for another user's request. Labels for step codes live in the frontend.
