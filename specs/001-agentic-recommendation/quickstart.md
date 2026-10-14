# Quickstart: Goal-Checked Recommendations

Prereq: `docker compose up` with a real `ANTHROPIC_API_KEY`, corpus loaded and embedded, frontend on http://localhost:3000.

## US1: recommendations meet the targets

1. Sign in, open Goals, set fiber to 30 g (others empty).
2. AI search: "something warm for lunch".
   Expected: 3 recipes, each showing a fiber check (target 10 g per meal, met at ≥ 8 g); most or all met.
3. AI search: "low carb dinner" with a carb goal of 300 g.
   Expected: the carb check reads "at most" (the request wins over the goal).
4. Clear all goals; AI search: "a quick pasta".
   Expected: 3 recipes, no goal checks, no unmet note.
5. Set calories to 300/day; AI search: "a hearty stew".
   Expected: 3 recipes and a note that the calories target isn't met by any of them.

## US2: live progress

1. Submit any AI search and watch the panel.
   Expected within 2 s: "Understanding your request", then the following steps tick off in order; "Widening the search" only in step 5 above.
2. Stop the worker (`docker compose stop worker`) and submit.
   Expected: progress stays empty, then the existing error after the deadline; never a frozen step list.

## SC-001 sample run (by hand, before shipping)

Run 10 requests × 3 goal profiles; count results whose goal checks are all met where the corpus has ≥ 3 such recipes. Target ≥ 80%.
