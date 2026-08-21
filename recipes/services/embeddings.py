"""Thin wrapper around the Voyage AI embeddings API.

This module is the seam patched by tests (`recipes.services.embeddings.embed_documents`
/ `embed_query`) so that ingestion and retrieval logic can be exercised without
real network calls.
"""

from django.conf import settings

EMBEDDING_MODEL = "voyage-3-lite"

_client = None


def _get_client():
    global _client
    if _client is None:
        import voyageai

        _client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
    return _client


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed recipe text at ingestion time."""
    if not texts:
        return []
    result = _get_client().embed(texts, model=EMBEDDING_MODEL, input_type="document")
    return result.embeddings


def embed_query(text: str) -> list[float]:
    """Embed a user's prompt at query time."""
    result = _get_client().embed([text], model=EMBEDDING_MODEL, input_type="query")
    return result.embeddings[0]
