"""In-repo adapters for the AI search seams (queries/services/resolution.py).

Passed straight to a `Resolver` in tests. No patching by import path.
"""

from typing import Any

from django.conf import settings

from queries.services.resolution import Interpretation, Pick


class FakeInterpreter:
    """Searches for the prompt as written and reads no nutrients from it."""

    def interpret(self, prompt: str) -> Interpretation:
        return Interpretation(search_phrase=prompt)


class FakeEmbedder:
    """Maps every prompt to `vector` (all zeros unless a test sets it)."""

    def __init__(self) -> None:
        self.vector = [0.0] * settings.EMBEDDING_DIMENSIONS

    def embed_query(self, text: str) -> list[float]:
        return list(self.vector)


class FakePicker:
    """Picks the first `count` shortlisted recipes, unless `script` says otherwise.

    Each `script` entry is consumed by one call: a list of picks to return, or
    an exception to raise. `shortlists` records what each call was shown."""

    def __init__(self) -> None:
        self.script: list[list[Pick] | Exception] = []
        self.shortlists: list[list[dict[str, Any]]] = []

    def pick(self, prompt: str, shortlist: list[dict[str, Any]], count: int) -> list[Pick]:
        self.shortlists.append(shortlist)
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, Exception):
                raise step
            return step
        return [Pick(c["recipe_id"], f"Picked {c['recipe_name']}.") for c in shortlist[:count]]
