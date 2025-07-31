"""Unit tests for HNSW delete functionality."""

import pytest

from mcp_the_force.vectorstores.hnsw.hnsw_vectorstore import HnswVectorStoreClient


@pytest.mark.asyncio
async def test_delete_store_files(tmp_path):
    """Test that delete removes store files from disk."""
    client = HnswVectorStoreClient(persist=True)
    client.persistence_dir = tmp_path

    # Manually create files to simulate a persisted store
    store_id = "hnsw_test123"
    index_path = tmp_path / f"{store_id}.bin"
    meta_path = tmp_path / f"{store_id}.json"

    # Create dummy files
    index_path.write_bytes(b"dummy index data")
    meta_path.write_text('{"chunks": []}')

    # Verify files exist
    assert index_path.exists()
    assert meta_path.exists()

    # Delete the store
    await client.delete(store_id)

    # Verify files are gone
    assert not index_path.exists(), "Index file should be deleted"
    assert not meta_path.exists(), "Metadata file should be deleted"


@pytest.mark.asyncio
async def test_delete_nonexistent_store(tmp_path):
    """Test that deleting a non-existent store doesn't raise an error."""
    client = HnswVectorStoreClient(persist=True)
    client.persistence_dir = tmp_path

    # Should not raise an error
    await client.delete("nonexistent_store_id")


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

    # Now test with only index file
    store_id2 = "hnsw_partial2"
    index_path = tmp_path / f"{store_id2}.bin"
    index_path.write_bytes(b"dummy")

    assert index_path.exists()

    await client.delete(store_id2)

    assert not index_path.exists()
