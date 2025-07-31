"""Simplified manager cleanup tests for HNSW vector store."""

import pytest
import time

from mcp_the_force.vectorstores.manager import VectorStoreManager
from mcp_the_force.vector_store_cache import VectorStoreCache


@pytest.fixture
async def manager_with_test_db(tmp_path):
    """Create a VectorStoreManager with test database."""
    db_path = tmp_path / "test_vector_stores.db"
    manager = VectorStoreManager(provider="hnsw")
    # Override the database path
    manager.vector_store_cache = VectorStoreCache(
        db_path=str(db_path),
        ttl=7200,  # 2 hours default
        purge_probability=0.0,  # Disable automatic purge for tests
    )

    # Mock the client delete method to track calls
    delete_calls = []

    class MockClient:
        def __init__(self):
            self.provider = "hnsw"

        async def delete(self, store_id):
            delete_calls.append(store_id)

        async def get(self, store_id):
            # Return a mock store
            class MockStore:
                id = store_id
                provider = "hnsw"

                async def add_files(self, files):
                    pass

                async def search(self, query, k=20):
                    return []

            return MockStore()

        async def create(self, name, ttl_seconds=None):
            class MockStore:
                id = f"hnsw_{time.time_ns() % 100000000:08x}"
                provider = "hnsw"

                async def add_files(self, files):
                    pass

                async def search(self, query, k=20):
                    return []

            return MockStore()

    # Inject mock client
    manager._client_cache["hnsw"] = MockClient()
    manager.delete_calls = delete_calls

    yield manager
    # Cleanup
    manager.vector_store_cache.close()


@pytest.mark.asyncio
async def test_session_store_cleanup(manager_with_test_db):
    """Test that expired session stores are deleted during cleanup."""
    # Create a session-based store with very short TTL
    session_id = "test-session-123"
    result = await manager_with_test_db.create(
        files=[],
        session_id=session_id,
        ttl_seconds=1,  # Expire in 1 second
    )

    assert result is not None
    store_id = result["store_id"]

    # Wait for expiration
    time.sleep(2)

    # Run cleanup
    cleaned_count = await manager_with_test_db.cleanup_expired()
    assert cleaned_count == 1

    # Verify delete was called
    assert store_id in manager_with_test_db.delete_calls

    # Verify store was removed from cache
    stores = await manager_with_test_db.vector_store_cache.get_expired_stores()
    assert len(stores) == 0


@pytest.mark.asyncio
async def test_protected_store_not_cleaned(manager_with_test_db):
    """Test that protected stores are NOT deleted even when expired."""
    # Create a named, protected store with very short TTL
    name = "test-memory-store"
    result = await manager_with_test_db.create(
        files=[],
        name=name,
        protected=True,  # Mark as protected
        ttl_seconds=1,  # Expire in 1 second
    )

    assert result is not None
    store_id = result["store_id"]

    # Wait for theoretical expiration
    time.sleep(2)

    # Run cleanup
    cleaned_count = await manager_with_test_db.cleanup_expired()
    assert cleaned_count == 0  # Nothing should be cleaned

    # Verify delete was NOT called
    assert store_id not in manager_with_test_db.delete_calls

    # Verify the store is not in expired list (because it's protected)
    expired_stores = await manager_with_test_db.vector_store_cache.get_expired_stores()
    assert len(expired_stores) == 0


@pytest.mark.asyncio
async def test_multiple_stores_cleanup(manager_with_test_db):
    """Test cleanup of multiple stores with mixed protection status."""
    stores_created = []

    # Session store 1 (should be deleted)
    result1 = await manager_with_test_db.create(
        files=[], session_id="session1", ttl_seconds=1
    )
    stores_created.append(("session1", result1["store_id"], False))

    # Session store 2 (should be deleted)
    result2 = await manager_with_test_db.create(
        files=[], session_id="session2", ttl_seconds=1
    )
    stores_created.append(("session2", result2["store_id"], False))

    # Protected store (should NOT be deleted)
    result3 = await manager_with_test_db.create(
        files=[], name="protected-memory", protected=True, ttl_seconds=1
    )
    stores_created.append(("protected", result3["store_id"], True))

    # Wait for expiration
    time.sleep(2)

    # Run cleanup
    cleaned_count = await manager_with_test_db.cleanup_expired()
    assert cleaned_count == 2  # Only session stores should be cleaned

    # Verify correct stores were deleted
    for name, store_id, is_protected in stores_created:
        if is_protected:
            assert store_id not in manager_with_test_db.delete_calls, (
                f"Protected store {name} should not be deleted"
            )
        else:
            assert store_id in manager_with_test_db.delete_calls, (
                f"Session store {name} should be deleted"
            )
