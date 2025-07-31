"""Integration tests for HNSW persistence functionality.

These tests use real hnswlib and sentence-transformers libraries.
"""

import pytest
import json
import os

from mcp_the_force.vectorstores.protocol import VSFile
from mcp_the_force.vectorstores.hnsw.hnsw_vectorstore import HnswVectorStoreClient

# Skip all tests in this module if in mock mode
pytestmark = pytest.mark.skipif(
    os.getenv("MCP_ADAPTER_MOCK") == "1",
    reason="HNSW persistence tests require real HNSW implementation",
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_persistence_roundtrip(tmp_path):
    """Test saving and loading a vector store."""
    # Create client with persistence enabled
    client = HnswVectorStoreClient(persist=True)
    client.persistence_dir = tmp_path

    # Create store and add files
    store = await client.create(name="test-persist")
    store_id = store.id

    files = [VSFile(path="/test.txt", content="The secret is hnswlib")]
    await store.add_files(files)

    # Check files were created
    index_path = tmp_path / f"{store_id}.bin"
    meta_path = tmp_path / f"{store_id}.json"

    assert index_path.exists(), "Index file not created"
    assert meta_path.exists(), "Metadata file not created"

    # Verify metadata content
    with open(meta_path, "r") as f:
        metadata = json.load(f)
    assert len(metadata) == 1
    assert metadata[0]["text"] == "The secret is hnswlib"
    assert metadata[0]["source"] == "/test.txt"

    # Create new client and load the store
    client2 = HnswVectorStoreClient(persist=True)
    client2.persistence_dir = tmp_path

    loaded_store = await client2.get(store_id=store_id)

    assert loaded_store.id == store_id
    assert loaded_store.provider == "hnsw"

    # Search should work
    results = await loaded_store.search("hnswlib")
    assert len(results) > 0
    assert "hnswlib" in results[0].content.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_atomic_save(tmp_path):
    """Test that saves are atomic using temp files."""
    client = HnswVectorStoreClient(persist=True)
    client.persistence_dir = tmp_path

    store = await client.create(name="test-atomic")
    store_id = store.id

    # Add a file
    await store.add_files([VSFile(path="test.txt", content="test")])

    # Check no temp files remain
    temp_files = list(tmp_path.glob("*.tmp"))
    assert len(temp_files) == 0, f"Temp files found: {temp_files}"

    # Check actual files exist
    assert (tmp_path / f"{store_id}.bin").exists()
    assert (tmp_path / f"{store_id}.json").exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_store(tmp_path):
    """Test that delete removes store files from disk."""
    client = HnswVectorStoreClient(persist=True)
    client.persistence_dir = tmp_path

    # Create and persist a store
    store = await client.create(name="test-delete")
    store_id = store.id

    # Add some data to ensure files are created
    await store.add_files([VSFile(path="test.txt", content="data to delete")])

    # Verify files exist
    index_path = tmp_path / f"{store_id}.bin"
    meta_path = tmp_path / f"{store_id}.json"
    assert index_path.exists()
    assert meta_path.exists()

    # Delete the store
    await client.delete(store_id)

    # Verify files are gone
    assert not index_path.exists(), "Index file should be deleted"
    assert not meta_path.exists(), "Metadata file should be deleted"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_nonexistent_store(tmp_path):
    """Test that deleting a non-existent store doesn't raise an error."""
    client = HnswVectorStoreClient(persist=True)
    client.persistence_dir = tmp_path

    # Should not raise an error
    await client.delete("nonexistent_store_id")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_partial_store(tmp_path):
    """Test deletion when only one file exists (corrupted state)."""
    client = HnswVectorStoreClient(persist=True)
    client.persistence_dir = tmp_path

    # Create only a metadata file (simulating corruption)
    store_id = "hnsw_partial"
    meta_path = tmp_path / f"{store_id}.json"
    meta_path.write_text('{"chunks": []}')

    assert meta_path.exists()

    # Delete should handle this gracefully
    await client.delete(store_id)

    # File should be gone
    assert not meta_path.exists()
