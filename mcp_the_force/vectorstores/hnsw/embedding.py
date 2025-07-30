"""Embedding model management for HNSW vector store."""

from threading import Lock

# Global instance and lock for thread-safe lazy initialization
_model = None
_lock = Lock()


def _load_sentence_transformer():
    """
    Isolated import so that tests can monkey-patch this function instead
    of wrestling with sys.modules.
    """
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("paraphrase-MiniLM-L3-v2")


def get_embedding_model():
    """
    Returns a thread-safe, singleton instance of the embedding model.

    The real model is *not* imported until the first real call, which
    means test suites can patch `_load_sentence_transformer()` (or the
    whole module) long before any heavy downloads start.
    """
    global _model
    if _model is None:
        with _lock:
            if _model is None:  # double-checked locking
                _model = _load_sentence_transformer()
    return _model


def get_embedding_dimensions():
    """Returns the dimension size of the embedding model."""
    return 384  # Hardcoded for the chosen model for efficiency
