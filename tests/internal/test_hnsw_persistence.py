"""Integration tests for HNSW persistence functionality.

These tests use real hnswlib and sentence-transformers libraries.
"""

import pytest
import json

from mcp_the_force.vectorstores.protocol import VSFile
from mcp_the_force.vectorstores.hnsw.hnsw_vectorstore import HnswVectorStoreClient


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
