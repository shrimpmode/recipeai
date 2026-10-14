# Quickstart: Decline Off-Topic Requests

Prereq: `docker compose up` with a real `ANTHROPIC_API_KEY`; `docker compose exec web python manage.py migrate`.

1. AI search: "write me a poem about the sea".
   Expected: "Understanding your request", then "I can only help with meals and recipes…", no cards, no error.
2. AI search: "I'm starving", then "something light".
   Expected: 3 recipes each, as before.

## SC-003 eval

`docker compose exec worker python manage.py eval_interpreter` runs the prompts below against the real model and exits non-zero below the thresholds (queries/management/commands/eval_interpreter.py). 2026-10-14, claude-haiku-4-5: 10/10 declined, 0/20 wrongly declined.

- Off topic (expect declined, ≥ 9 of 10): write me a poem about the sea · what's the weather tomorrow · fix my Python code · who won the world cup · translate hello into French · tell me a joke · how do I change a tyre · summarise this article · book me a flight · what is 17 × 23
- Food (expect recipes, none of 20 declined): I'm starving · something light · high protein breakfast · comfort food · low carb dinner · what can I make with eggs · quick lunch · something warm and high in fibre · vegan dessert · healthy snack · I'm sad, cook me something comforting · how much fiber should I eat · pasta · meal prep for the week · post-workout meal · kid-friendly dinner · something spicy · a light salad · gluten free bread · soup
