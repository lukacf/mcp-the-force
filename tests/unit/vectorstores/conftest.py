"""Pytest configuration for vectorstore tests."""

import pytest
import numpy as np
from pathlib import Path
from typing import Protocol


# Protocol matching what HNSW expects
class IndexProtocol(Protocol):
    def init_index(self, max_elements: int, ef_construction: int, M: int) -> None: ...
    def add_items(self, vectors: np.ndarray, ids: list[int]) -> None: ...
    def get_current_count(self) -> int: ...
    def knn_query(
        self, queries: np.ndarray, k: int
    ) -> tuple[list[list[int]], list[list[float]]]: ...
    def save_index(self, path: str) -> None: ...
    def load_index(self, path: str, max_elements: int) -> None: ...


class FakeIndex:
    """Lightweight fake HNSW index for testing."""

    def __init__(self, *args, **kwargs):
        self._vectors = {}  # id -> vector

    def init_index(self, max_elements: int, ef_construction: int, M: int) -> None:
        """No-op initialization."""
        pass

    def add_items(self, vectors: np.ndarray, ids: list[int]) -> None:
        """Store vectors in memory."""
        for i, vec_id in enumerate(ids):
            self._vectors[vec_id] = vectors[i]

    def get_current_count(self) -> int:
        """Return number of stored vectors."""
        return len(self._vectors)

    def knn_query(
        self, queries: np.ndarray, k: int = 10
    ) -> tuple[list[list[int]], list[list[float]]]:
        """Return deterministic dummy results."""
        num_results = min(k, len(self._vectors))
        if num_results == 0:
            return [[] for _ in range(len(queries))], [[] for _ in range(len(queries))]

        # Return first k items as results for each query
        vec_ids = list(self._vectors.keys())[:num_results]
        labels = [vec_ids for _ in range(len(queries))]
        dists = [[0.1] * num_results for _ in range(len(queries))]
        return labels, dists

    def save_index(self, path: str) -> None:
        """Touch file to simulate save."""
        Path(path).write_bytes(b"fake_index")

    def load_index(self, path: str, max_elements: int) -> None:
        """No-op load."""
        pass


def fake_index_factory(dim: int) -> IndexProtocol:
    """Factory that creates fake indices for testing."""
    return FakeIndex()


@pytest.fixture
def mock_embedding_model(monkeypatch):
    """Mock the embedding model to avoid loading sentence_transformers."""
    from unittest.mock import MagicMock

    mock_model = MagicMock()

    # Make encode return appropriately sized arrays based on input
    def mock_encode(texts):
        """Return random embeddings with correct shape."""
        if isinstance(texts, list):
            return np.random.rand(len(texts), 384)
        else:
            # Single text input
            return np.random.rand(1, 384)

    mock_model.encode.side_effect = mock_encode

    # Patch the loader function
    from mcp_the_force.vectorstores.hnsw import embedding

    monkeypatch.setattr(embedding, "_load_sentence_transformer", lambda: mock_model)
    monkeypatch.setattr(embedding, "_model", None)

    return mock_model


@pytest.fixture
def hnsw_test_client(mock_embedding_model):
    """Provides an HNSW client configured for unit testing."""
    from mcp_the_force.vectorstores.hnsw.hnsw_vectorstore import HnswVectorStoreClient

    return HnswVectorStoreClient(
        index_factory=fake_index_factory,
        persist=False,  # Disable filesystem operations
    )
