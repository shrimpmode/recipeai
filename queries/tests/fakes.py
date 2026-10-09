"""In-repo adapters for the AI search seams (queries/services/resolution.py).

Selected through settings in API-level tests (`use_fake_adapters`) or passed
straight to a `Resolver` in module tests. No patching by import path.
"""

from typing import Any

from django.conf import settings
from django.test import override_settings

from queries.services.resolution import Pick, default_resolver


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


use_fake_adapters = override_settings(
    AI_SEARCH_EMBEDDER="queries.tests.fakes.FakeEmbedder",
    AI_SEARCH_PICKER="queries.tests.fakes.FakePicker",
)


def fake_adapters() -> tuple[FakeEmbedder, FakePicker]:
    """A fresh resolver's fakes, for a test to script and inspect (call in setUp)."""
    default_resolver.cache_clear()
    resolver = default_resolver()
    assert isinstance(resolver.embedder, FakeEmbedder) and isinstance(resolver.picker, FakePicker)
    return resolver.embedder, resolver.picker
