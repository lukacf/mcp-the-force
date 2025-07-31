"""Embedding model management for HNSW vector store."""

import logging
from threading import Lock
import hashlib
import numpy as np

logger = logging.getLogger(__name__)

# Global instance and lock for thread-safe lazy initialization
_model = None
_lock = Lock()


class CachedEmbeddingModel:
    """Wrapper that adds caching to sentence transformer model."""

    def __init__(self, model):
        self._model = model
        # Simple LRU cache for embeddings (max 1000 entries)
        self._cache = {}
        self._cache_order = []
        self._max_cache_size = 1000

    def _get_cached_or_compute(self, text):
        """Get embedding from cache or compute it."""
        text_hash = hashlib.md5(text.encode()).hexdigest()

        if text_hash in self._cache:
            # Move to end (most recently used)
            self._cache_order.remove(text_hash)
            self._cache_order.append(text_hash)
            return self._cache[text_hash]

        # Compute embedding
        embedding = self._model.encode(text, convert_to_numpy=True)

        # Add to cache
        self._cache[text_hash] = embedding
        self._cache_order.append(text_hash)

        # Evict oldest if cache is full
        if len(self._cache) > self._max_cache_size:
            oldest = self._cache_order.pop(0)
            del self._cache[oldest]

        return embedding

    def encode(self, texts, **kwargs):
        """Encode texts with caching for individual strings."""
        # Handle single string
        if isinstance(texts, str):
            return self._get_cached_or_compute(texts)

        # Handle list of strings - cache each individually
        if isinstance(texts, list) and all(isinstance(t, str) for t in texts):
            results = []
            for text in texts:
                embedding = self._get_cached_or_compute(text)
                results.append(embedding)
            return np.array(results)

        # Fallback to original model for other cases
        return self._model.encode(texts, **kwargs)

    def __getattr__(self, name):
        """Forward all other attributes to the wrapped model."""
        return getattr(self._model, name)


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
    import os

    # Check if we should run in offline mode
    offline_mode = os.environ.get("HF_HUB_OFFLINE", "0") == "1"

    model = SentenceTransformer(
        "paraphrase-MiniLM-L3-v2", local_files_only=offline_mode
    )
    logger.info("HNSW embedding model loaded successfully")

    return model


def get_embedding_model():
    """
    Returns a thread-safe, singleton instance of the embedding model with caching.

    The real model is *not* imported until the first real call, which
    means test suites can patch `_load_sentence_transformer()` (or the
    whole module) long before any heavy downloads start.
    """
    global _model
    if _model is None:
        with _lock:
            if _model is None:  # double-checked locking
                base_model = _load_sentence_transformer()
                _model = CachedEmbeddingModel(base_model)
    return _model


def get_embedding_dimensions():
    """Returns the dimension size of the embedding model."""
    return 384  # Hardcoded for the chosen model for efficiency
