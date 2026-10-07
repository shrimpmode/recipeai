"""Thin wrapper around a local sentence-transformers embedding model.

Runs in-process (CPU inference), no API key or external network call at
query time. This module is the seam patched by tests
(`recipes.services.embeddings.embed_documents` / `embed_query`) so that
ingestion and retrieval logic can be exercised without loading the real
model.
"""

EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed recipe text at ingestion time."""
    if not texts:
        return []
    return _get_model().encode(texts, convert_to_numpy=True, show_progress_bar=False).tolist()


def embed_query(text: str) -> list[float]:
    """Embed a user's prompt at query time."""
    return embed_documents([text])[0]


class LocalEmbedder:
    """`embedding_backfill.Embedder` adapter for the in-process model."""

    model_id = EMBEDDING_MODEL

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_documents(texts)
