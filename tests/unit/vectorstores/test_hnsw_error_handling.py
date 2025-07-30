"""Tests for HNSW error handling and robustness."""

import pytest
import logging
from pathlib import Path

from mcp_the_force.vectorstores.hnsw.hnsw_vectorstore import HnswVectorStoreClient
from mcp_the_force.vectorstores.errors import VectorStoreError
from mcp_the_force.vectorstores.protocol import VSFile

# Import the mock fixture
pytest_plugins = ["tests.unit.vectorstores.conftest"]


@pytest.mark.asyncio
async def test_save_permission_error(tmp_path, monkeypatch, mock_embedding_model):
    """Test handling of permission errors during save."""
    from tests.unit.vectorstores.conftest import fake_index_factory

    client = HnswVectorStoreClient(index_factory=fake_index_factory, persist=True)
    client.persistence_dir = tmp_path / "readonly"

    # Mock mkdir to raise PermissionError
    original_mkdir = Path.mkdir

    def mock_mkdir(self, *args, **kwargs):
        if "readonly" in str(self):
            raise PermissionError("Permission denied")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)

    store = await client.create(name="test-perms")

    # This should raise VectorStoreError due to permission issue
    with pytest.raises(VectorStoreError, match="Cannot create persistence directory"):
        await store.add_files([VSFile(path="test.txt", content="data")])


@pytest.mark.asyncio
@pytest.mark.skip(reason="Test times out due to embedding model download")
async def test_save_disk_full_error(tmp_path, monkeypatch, mock_embedding_model):
    """Test handling of disk full errors during save."""
    from tests.unit.vectorstores.conftest import fake_index_factory

    client = HnswVectorStoreClient(index_factory=fake_index_factory, persist=True)
    client.persistence_dir = tmp_path

    store = await client.create(name="test-disk")

    # Create a mock index that raises when saving
    class FailingSaveIndex:
        def __init__(self):
            self._vectors = {}

        def init_index(self, *args, **kwargs):
            pass

        def add_items(self, vectors, ids):
            for i, vec_id in enumerate(ids):
                self._vectors[vec_id] = vectors[i]

        def get_current_count(self):
            return len(self._vectors)

        def save_index(self, path):
            # Simulate save failure
            raise OSError("No space left on device")

        def resize_index(self, new_max):
            pass

    # Override the store's index
    store._index = FailingSaveIndex()
    store._index.init_index(10000, 200, 16)

    # This should raise VectorStoreError due to disk full
    with pytest.raises(VectorStoreError, match="Failed to save HNSW index"):
        await store.add_files([VSFile(path="test.txt", content="data")])


@pytest.mark.asyncio
async def test_load_corrupted_metadata(tmp_path):
    """Test handling of corrupted metadata files."""
    client = HnswVectorStoreClient(persist=True)
    client.persistence_dir = tmp_path

    # Create corrupted metadata file
    store_id = "hnsw_corrupted"
    meta_path = tmp_path / f"{store_id}.json"
    meta_path.write_text("{ invalid json ]")

    # Create dummy index file
    index_path = tmp_path / f"{store_id}.bin"
    index_path.write_bytes(b"dummy")

    # Should raise VectorStoreError for corrupted metadata
    with pytest.raises(VectorStoreError, match="Corrupted metadata file"):
        await client.get(store_id)


@pytest.mark.asyncio
async def test_load_missing_index(tmp_path):
    """Test handling of missing index file."""
    client = HnswVectorStoreClient(persist=True)
    client.persistence_dir = tmp_path

    # Create only metadata file
    store_id = "hnsw_no_index"
    meta_path = tmp_path / f"{store_id}.json"
    meta_path.write_text('[{"text": "test", "source": "test.txt"}]')

    # Should raise VectorStoreError for missing index (detected early)
    with pytest.raises(VectorStoreError, match="Store with ID .* not found on disk"):
        await client.get(store_id)


@pytest.mark.asyncio
async def test_load_permission_denied(tmp_path):
    """Test handling of permission denied when loading."""
    client = HnswVectorStoreClient(persist=True)
    client.persistence_dir = tmp_path

    # Create files
    store_id = "hnsw_no_perms"
    meta_path = tmp_path / f"{store_id}.json"
    meta_path.write_text("[]")
    index_path = tmp_path / f"{store_id}.bin"
    index_path.write_bytes(b"dummy")

    # Make metadata file unreadable
    meta_path.chmod(0o000)

    try:
        # Should raise VectorStoreError for permission denied
        with pytest.raises(VectorStoreError, match="Permission denied"):
            await client.get(store_id)
    finally:
        # Restore permissions for cleanup
        meta_path.chmod(0o644)


@pytest.mark.asyncio
async def test_index_resize_logging(tmp_path, caplog, mock_embedding_model):
    """Test that index resize warning is logged when resize is not supported."""

    # Create a fake index that doesn't have resize_index
    class NoResizeIndex:
        def __init__(self):
            self._vectors = {}

        def init_index(self, *args, **kwargs):
            pass

        def add_items(self, vectors, ids):
            for i, vec_id in enumerate(ids):
                self._vectors[vec_id] = vectors[i]

        def get_current_count(self):
            return len(self._vectors)

        def save_index(self, path):
            Path(path).write_bytes(b"fake")

        def load_index(self, path, max_elements):
            pass

        # Note: no resize_index method!

    def no_resize_factory(dim):
        return NoResizeIndex()

    # Create client with index that doesn't support resize
    client = HnswVectorStoreClient(index_factory=no_resize_factory, persist=False)

    store = await client.create(name="test-resize")
    # Set a very small max_elements to trigger resize
    store._max_elements = 2

    # Add files that will exceed capacity
    files = [
        VSFile(path=f"file{i}.txt", content=f"Content {i}\n\nParagraph 2")
        for i in range(3)
    ]

    # Clear any existing logs and set log level
    caplog.clear()
    # Ensure we capture logs from the hnsw module
    with caplog.at_level(
        logging.WARNING, logger="mcp_the_force.vectorstores.hnsw.hnsw_vectorstore"
    ):
        await store.add_files(files)

        # Check that warning was logged
        assert any(
            "Index resize not supported" in record.message for record in caplog.records
        )


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires actual model loading")
async def test_model_download_logging(caplog, monkeypatch):
    """Test that model download is logged on first load."""
    from mcp_the_force.vectorstores.hnsw import embedding

    # Reset the model singleton
    monkeypatch.setattr(embedding, "_model", None)

    # Clear logs
    caplog.clear()

    # Trigger model load
    _ = embedding.get_embedding_model()

    # Check logs
    assert any(
        "Initializing HNSW embedding model" in record.message
        for record in caplog.records
    )
    assert any(
        "First-time setup may download" in record.message for record in caplog.records
    )
