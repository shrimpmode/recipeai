"""Thin wrapper around the OpenAI embeddings API.

This module is the seam patched by tests (`recipes.services.embeddings.embed_documents`
/ `embed_query`) so that ingestion and retrieval logic can be exercised without
real network calls.
"""

from django.conf import settings

EMBEDDING_MODEL = "text-embedding-3-small"

_client = None


def _get_client():
    global _client
    if _client is None:
        import openai

        _client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed recipe text at ingestion time."""
    if not texts:
        return []
    response = _get_client().embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )
    return [item.embedding for item in response.data]


def embed_query(text: str) -> list[float]:
    """Embed a user's prompt at query time."""
    return embed_documents([text])[0]
