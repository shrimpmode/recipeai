"""`RecipePicker` adapter for the Claude Messages API (see queries/services/resolution.py).

Retries belong to the Celery task, so the SDK's own retries are off and each
call is bounded by CLAUDE_TIMEOUT_SECONDS. Provider errors are classified at
this seam: requests Claude will never accept (auth, permissions, malformed)
become `PermanentFailure`; everything else (rate limits, overload, 5xx,
timeouts, connection errors) propagates unchanged and is retried.
"""

import json
import logging
import re
import time
from typing import Any

import anthropic
from django.conf import settings

from queries.services.resolution import PermanentFailure, Pick, UnusablePicks

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

# Below 500, only these mean "try again later"; any other 4xx will fail the same way every time.
_RETRYABLE_CLIENT_ERRORS = {408, 409, 429}

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _system_prompt(count: int) -> str:
    return (
        "You are a nutrition assistant. Given a user's request and a shortlist of "
        "candidate recipes with their per-serving nutrition data, select the "
        f"{count} recipes that best match the request and write a short "
        "(1-2 sentence) description for each explaining why it fits. "
        'Respond ONLY with a JSON array of objects, each with keys "recipe_id" '
        '(integer, matching a candidate\'s id) and "description" (string). Do not '
        "wrap the JSON in markdown code fences or add any other text. "
        f"Return exactly {count} objects."
    )


class ClaudePicker:
    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self._client = client or anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.CLAUDE_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def pick(self, prompt: str, shortlist: list[dict[str, Any]], count: int) -> list[Pick]:
        started = time.monotonic()
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=_system_prompt(count),
                messages=[{"role": "user", "content": json.dumps({"user_request": prompt, "candidates": shortlist})}],
            )
        except anthropic.APIStatusError as exc:
            if exc.status_code < 500 and exc.status_code not in _RETRYABLE_CLIENT_ERRORS:
                raise PermanentFailure(f"Claude rejected the request: HTTP {exc.status_code}") from exc
            raise
        logger.info(
            "claude_selection_completed",
            extra={
                "model": MODEL,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "stop_reason": response.stop_reason,
                # Quote this when asking Anthropic support about a specific call.
                "anthropic_request_id": getattr(response, "_request_id", None),
            },
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return _parse_picks(text)


def _parse_picks(text: str) -> list[Pick]:
    try:
        payload = json.loads(_CODE_FENCE_RE.sub("", text.strip()))
        if not isinstance(payload, list):
            raise ValueError("not a JSON array")
        picks = []
        for item in payload:
            recipe_id, description = item["recipe_id"], item["description"]
            if isinstance(recipe_id, bool) or not isinstance(recipe_id, int) or not isinstance(description, str):
                raise ValueError(f"bad pick {item!r}")
            picks.append(Pick(recipe_id=recipe_id, description=description))
        return picks
    except (ValueError, TypeError, KeyError) as exc:  # JSONDecodeError is a ValueError
        logger.warning("claude_selection_unparseable", extra={"response_preview": text[:500]})
        raise UnusablePicks(f"unparseable picks: {exc}") from exc
