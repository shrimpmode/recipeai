"""Thin wrapper around the Claude API call that picks and describes the final
recipes from a shortlist. This module is the seam patched by tests.
"""

import json
import re

from django.conf import settings

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are a nutrition assistant. Given a user's request and a shortlist of "
    "candidate recipes with their per-serving nutrition data, select the "
    f"{settings.RESULT_COUNT} recipes that best match the request and write a short "
    "(1-2 sentence) description for each explaining why it fits. "
    'Respond ONLY with a JSON array of objects, each with keys "recipe_id" '
    '(integer, matching a candidate\'s id) and "description" (string). Do not '
    "wrap the JSON in markdown code fences or add any other text. "
    f"Return exactly {settings.RESULT_COUNT} objects."
)

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def select_and_describe(prompt: str, candidates: list[dict]) -> list[dict]:
    """`candidates`: dicts with at least `recipe_id` and per-serving nutrition
    fields. Returns a list of {"recipe_id": int, "description": str}."""
    user_content = json.dumps({"user_request": prompt, "candidates": candidates})

    response = _get_client().messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return json.loads(_CODE_FENCE_RE.sub("", text.strip()))
