"""Embedding model management for HNSW vector store."""

import logging
from threading import Lock

logger = logging.getLogger(__name__)

# Global instance and lock for thread-safe lazy initialization
_model = None
_lock = Lock()


def _load_sentence_transformer():
    """
    Isolated import so that tests can monkey-patch this function instead
    of wrestling with sys.modules.
    """
    logger.info(
        "Initializing HNSW embedding model. First-time setup may download "
        "~45MB model data. This is a one-time operation..."
    )

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("paraphrase-MiniLM-L3-v2")
    logger.info("HNSW embedding model loaded successfully")

    return model


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
