"""Tests for HNSW vector store implementation using dependency injection."""

import pytest
import json

from mcp_the_force.vectorstores.protocol import VSFile
from mcp_the_force.vectorstores import registry


@pytest.mark.asyncio
async def test_create_vector_store(hnsw_test_client):
    """Test that a new vector store can be created."""
    store = await hnsw_test_client.create(name="test-store")

    assert store.id.startswith("hnsw_")
    assert store.provider == "hnsw"
    assert hasattr(store, "add_files")
    assert hasattr(store, "search")
    assert hasattr(store, "delete_files")


@pytest.mark.asyncio
async def test_add_and_search(hnsw_test_client):
    """Test adding files and searching."""
    # Create store
    store = await hnsw_test_client.create(name="demo")

    # Add files
    files = [
        VSFile(
            path="doc1.txt", content="The quick brown fox.\n\nJumps over the lazy dog."
        ),
        VSFile(path="doc2.txt", content="Python is great.\n\nFor data science."),
    ]
    file_ids = await store.add_files(files)

    assert len(file_ids) == 2

    # Search
    results = await store.search("dog", k=1)
    assert len(results) > 0
    # Since we use a fake index, we can't test exact matches
    # but we can verify the structure
    assert hasattr(results[0], "content")
    assert hasattr(results[0], "score")
    assert hasattr(results[0], "file_id")


@pytest.mark.asyncio
async def test_persistence_disabled(hnsw_test_client, tmp_path):
    """Test that persistence is disabled in test mode."""
    # Override persistence dir
    hnsw_test_client.persistence_dir = tmp_path

    store = await hnsw_test_client.create(name="test")
    await store.add_files([VSFile(path="test.txt", content="test content")])

    # Check that no files were created (persistence disabled)
    assert len(list(tmp_path.glob("*.bin"))) == 0
    assert len(list(tmp_path.glob("*.json"))) == 0


@pytest.mark.asyncio
async def test_registry_integration(hnsw_test_client):
    """Test that HNSW provider can be registered."""
    # Just verify the existing registration works
    providers = registry.list_providers()
    assert "hnsw" in providers

    # Get client from registry (the production one)
    client = registry.get_client("hnsw")
    assert client.provider == "hnsw"


@pytest.mark.asyncio
async def test_empty_search(hnsw_test_client):
    """Test searching an empty store."""
    store = await hnsw_test_client.create(name="empty")
    results = await store.search("anything")
    assert results == []


@pytest.mark.asyncio
async def test_add_empty_file_list(hnsw_test_client):
    """Test adding empty file list."""
    store = await hnsw_test_client.create(name="test")
    file_ids = await store.add_files([])
    assert file_ids == []


@pytest.mark.asyncio
@pytest.mark.skip(reason="Integration test - requires real hnswlib")
async def test_persistence_enabled(tmp_path):
    """Test actual persistence when enabled."""
    from mcp_the_force.vectorstores.hnsw.hnsw_vectorstore import HnswVectorStoreClient

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


@pytest.mark.asyncio
@pytest.mark.skip(reason="Integration test - requires real hnswlib")
async def test_load_persisted_store(tmp_path):
    """Test loading a persisted store."""
    from mcp_the_force.vectorstores.hnsw.hnsw_vectorstore import HnswVectorStoreClient

    # Create and persist a store
    client1 = HnswVectorStoreClient(persist=True)
    client1.persistence_dir = tmp_path

    store1 = await client1.create(name="test-load")
    store_id = store1.id
    await store1.add_files([VSFile(path="/a.txt", content="Hello world")])

    # Create new client and load the store
    client2 = HnswVectorStoreClient(persist=True)
    client2.persistence_dir = tmp_path

    loaded_store = await client2.get(store_id=store_id)

    assert loaded_store.id == store_id
    assert loaded_store.provider == "hnsw"

    # Should be able to search the loaded store
    results = await loaded_store.search("world")
    assert len(results) > 0
