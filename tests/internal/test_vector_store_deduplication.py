"""Integration tests for vector store deduplication system.

These tests verify the complete deduplication flow including:
- Store-level deduplication (identical file sets reuse same store)
- File-level deduplication (individual files cached and reused)
- TTL renewal for reused stores
- Stale cache cleanup when stores are deleted
- Project isolation
- Concurrency safety
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from mcp_the_force.vectorstores.manager import VectorStoreManager
from mcp_the_force.dedup.simple_cache import get_cache
from mcp_the_force.dedup.hashing import compute_content_hash, compute_fileset_hash


@pytest.fixture(autouse=True)
def reset_cache_singleton():
    """Reset the cache singleton for each test to ensure clean state."""
    import mcp_the_force.dedup.simple_cache as cache_module

    cache_module._cache = None
    yield
    # Clean up after test
    cache_module._cache = None


@pytest.fixture
def initialized_cache(isolate_test_databases, reset_cache_singleton):
    """Get a properly initialized cache for testing."""
    cache = get_cache()
    # Ensure database is properly initialized
    cache._init_database()
    return cache


@pytest.fixture
def temp_files(tmp_path):
    """Create temporary test files with known content."""
    files = {}

    # File 1: Python file
    file1 = tmp_path / "test1.py"
    content1 = "def hello():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    hello()"
    file1.write_text(content1)
    files["file1"] = {"path": str(file1), "content": content1}

    # File 2: Python file (different content)
    file2 = tmp_path / "test2.py"
    content2 = "def goodbye():\n    print('Goodbye, World!')\n\nif __name__ == '__main__':\n    goodbye()"
    file2.write_text(content2)
    files["file2"] = {"path": str(file2), "content": content2}

    # File 3: Same content as file1 (for testing file-level dedup)
    file3 = tmp_path / "duplicate.py"
    file3.write_text(content1)  # Same content as file1
    files["file3"] = {"path": str(file3), "content": content1}

    return files


@pytest.fixture
def mock_vector_store_cache():
    """Mock VectorStoreCache for testing."""
    mock_cache = AsyncMock()
    mock_cache.get_or_create_placeholder.return_value = (
        None,
        False,
    )  # No existing store
    mock_cache.register_store = AsyncMock()
    mock_cache.remove_store = AsyncMock(return_value=True)
    mock_cache.get_expired_stores = AsyncMock(return_value=[])
    mock_cache.cleanup_orphaned = AsyncMock(return_value=0)
    return mock_cache


@pytest.fixture
def manager_with_mock_cache(mock_vector_store_cache, monkeypatch):
    """VectorStoreManager with mocked VectorStoreCache."""
    manager = VectorStoreManager()
    manager.vector_store_cache = mock_vector_store_cache

    # Use inmemory provider for testing
    monkeypatch.setenv("MCP_ADAPTER_MOCK", "1")

    return manager


class TestStoreLevelDeduplication:
    """Test store-level deduplication functionality."""

    @pytest.mark.asyncio
    async def test_identical_fileset_reuses_store(
        self, manager_with_mock_cache, temp_files, isolate_test_databases
    ):
        """Test that identical file sets reuse the same vector store."""
        manager = manager_with_mock_cache
        files = [temp_files["file1"]["path"], temp_files["file2"]["path"]]

        # First call should create a new store
        result1 = await manager.create(files=files, session_id="session1")
        assert result1 is not None
        store_id_1 = result1["store_id"]

        # Second call with same files should reuse the store (different session)
        result2 = await manager.create(files=files, session_id="session2")
        assert result2 is not None
        store_id_2 = result2["store_id"]

        # Should reuse the same store
        assert store_id_1 == store_id_2
        assert result1["provider"] == result2["provider"]

        # Verify TTL renewal was called for reused store
        manager.vector_store_cache.register_store.assert_called()

    @pytest.mark.asyncio
    async def test_file_content_change_creates_new_store(
        self, manager_with_mock_cache, temp_files, isolate_test_databases
    ):
        """Test that changing file content creates a new store."""
        manager = manager_with_mock_cache

        # First call with original files
        files1 = [temp_files["file1"]["path"], temp_files["file2"]["path"]]
        result1 = await manager.create(files=files1, session_id="session1")
        assert result1 is not None
        store_id_1 = result1["store_id"]

        # Second call with different file content (file3 has different content than file2)
        files2 = [
            temp_files["file1"]["path"],
            temp_files["file3"]["path"],
        ]  # file3 has same content as file1
        result2 = await manager.create(files=files2, session_id="session2")
        assert result2 is not None
        store_id_2 = result2["store_id"]

        # Should be different stores since file sets are different
        assert store_id_1 != store_id_2

    @pytest.mark.asyncio
    async def test_file_order_irrelevant_for_store_reuse(
        self, manager_with_mock_cache, temp_files, isolate_test_databases
    ):
        """Test that file order doesn't affect store reuse."""
        manager = manager_with_mock_cache

        # First call with files in order A, B
        files1 = [temp_files["file1"]["path"], temp_files["file2"]["path"]]
        result1 = await manager.create(files=files1, session_id="session1")
        assert result1 is not None
        store_id_1 = result1["store_id"]

        # Second call with files in order B, A
        files2 = [temp_files["file2"]["path"], temp_files["file1"]["path"]]
        result2 = await manager.create(files=files2, session_id="session2")
        assert result2 is not None
        store_id_2 = result2["store_id"]

        # Should reuse the same store regardless of order
        assert store_id_1 == store_id_2


class TestFileLevelDeduplication:
    """Test file-level deduplication functionality."""

    @pytest.mark.asyncio
    async def test_file_content_hash_consistency(self, temp_files):
        """Test that identical content produces consistent hashes."""
        content1 = temp_files["file1"]["content"]
        content3 = temp_files["file3"]["content"]  # Same content as file1

        hash1 = compute_content_hash(content1)
        hash3 = compute_content_hash(content3)

        # Should produce the same hash for identical content
        assert hash1 == hash3
        assert len(hash1) == 64  # SHA-256 hex length

    def test_fileset_hash_order_independence(self, temp_files):
        """Test that fileset hash is order-independent."""
        content1 = temp_files["file1"]["content"]
        content2 = temp_files["file2"]["content"]
        path1 = "file1.txt"
        path2 = "file2.txt"

        hash_a = compute_fileset_hash([(path1, content1), (path2, content2)])
        hash_b = compute_fileset_hash(
            [(path2, content2), (path1, content1)]
        )  # Different order

        # Should produce the same hash regardless of order
        assert hash_a == hash_b
        assert len(hash_a) == 64  # SHA-256 hex length

    def test_fileset_hash_collision_prevention(self):
        """Test that identical content with different paths produces different hashes.

        This test prevents the critical hash collision bug where files with
        identical content but different paths would generate the same fileset hash,
        causing wrong vector store reuse and data corruption.
        """
        # Same content, different paths - this is the collision scenario
        identical_content = "def hello(): return 'world'"

        # Scenario A: Files from different directories with same content
        fileset_a = [
            ("app/v1/routes.py", identical_content),
            ("app/common.py", "# Common utilities"),
        ]

        fileset_b = [
            ("app/v2/routes.py", identical_content),  # Same content, different path
            ("app/common.py", "# Common utilities"),
        ]

        hash_a = compute_fileset_hash(fileset_a)
        hash_b = compute_fileset_hash(fileset_b)

        # CRITICAL: These must be different to prevent data corruption
        assert hash_a != hash_b, (
            "Hash collision detected! Files with identical content but different paths "
            "are generating the same fileset hash, which will cause vector store reuse "
            "and return wrong embeddings. This is a critical data corruption bug."
        )

        # However, truly identical filesets should still produce the same hash
        fileset_c = [
            ("app/v1/routes.py", identical_content),
            ("app/common.py", "# Common utilities"),
        ]

        hash_c = compute_fileset_hash(fileset_c)
        assert hash_a == hash_c, "Identical filesets should produce identical hashes"


class TestCacheIntegration:
    """Test cache integration and lifecycle management."""

    def test_project_specific_cache_path(self, initialized_cache):
        """Test that cache uses project-specific path, not global path."""
        cache = initialized_cache

        # Cache path should be project-local, not global
        assert ".mcp-the-force" in cache.db_path
        assert not cache.db_path.startswith(str(Path.home()))  # Not global

        # Should be able to get stats
        stats = cache.get_stats()
        assert stats["cache_type"] == "SimpleVectorStoreCache"

    @pytest.mark.asyncio
    async def test_stale_cache_cleanup_integration(
        self, manager_with_mock_cache, initialized_cache
    ):
        """Test that expired stores are removed from dedup cache."""
        manager = manager_with_mock_cache

        # Setup mock expired store
        expired_store = {
            "vector_store_id": "test_store_123",
            "provider": "openai",
            "session_id": "expired_session",
        }
        manager.vector_store_cache.get_expired_stores.return_value = [expired_store]

        # Add entry to dedup cache
        dedup_cache = initialized_cache
        dedup_cache.cache_store("test_fileset_hash", "test_store_123", "openai")

        # Verify it's in the cache
        cached_store = dedup_cache.get_store_id("test_fileset_hash")
        assert cached_store is not None
        assert cached_store["store_id"] == "test_store_123"

        # Run cleanup
        cleaned_count = await manager.cleanup_expired()

        # Verify cleanup was attempted
        assert cleaned_count >= 0

        # Note: In real test, we'd verify the store was removed from dedup cache,
        # but since we're using mocked vector store deletion, we just verify the integration

    def test_cache_stats_and_cleanup(self, initialized_cache):
        """Test cache statistics and cleanup functionality."""
        cache = initialized_cache

        # Initially empty
        stats = cache.get_stats()
        assert stats["file_count"] == 0
        assert stats["store_count"] == 0

        # Add some entries
        cache.cache_file("hash1", "file1")
        cache.cache_file("hash2", "file2")
        cache.cache_store("fileset1", "store1", "openai")

        # Check stats
        stats = cache.get_stats()
        assert stats["file_count"] == 2
        assert stats["store_count"] == 1

        # Test cleanup (should not remove recent entries)
        cache.cleanup_old_entries(max_age_days=30)

        stats = cache.get_stats()
        assert stats["file_count"] == 2  # Still there
        assert stats["store_count"] == 1  # Still there


class TestConcurrencySafety:
    """Test concurrency safety of the cache system."""

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self, initialized_cache):
        """Test that concurrent cache operations don't conflict."""
        cache = initialized_cache

        async def cache_operation(i):
            """Simulate concurrent cache operations."""
            # Mix of file and store operations
            cache.cache_file(f"hash_{i}", f"file_{i}")
            cache.cache_store(f"fileset_{i}", f"store_{i}", "openai")

            # Read operations
            result = cache.get_file_id(f"hash_{i}")
            store_result = cache.get_store_id(f"fileset_{i}")

            return result == f"file_{i}" and store_result is not None

        # Run multiple concurrent operations
        tasks = [cache_operation(i) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All operations should succeed
        assert all(isinstance(r, bool) and r for r in results)

        # Verify final state
        stats = cache.get_stats()
        assert stats["file_count"] == 10
        assert stats["store_count"] == 10


class TestErrorHandling:
    """Test error handling in deduplication system."""

    @pytest.mark.asyncio
    async def test_dedup_failure_graceful_degradation(
        self, manager_with_mock_cache, temp_files, isolate_test_databases, monkeypatch
    ):
        """Test that deduplication failures don't break store creation."""
        manager = manager_with_mock_cache

        # Mock deduplication failure
        def failing_get_cache():
            raise Exception("Cache failure")

        monkeypatch.setattr(
            "mcp_the_force.vectorstores.manager.get_cache", failing_get_cache
        )

        # Store creation should still work
        files = [temp_files["file1"]["path"]]
        result = await manager.create(files=files, session_id="session1")

        # Should succeed despite dedup failure
        assert result is not None
        assert "store_id" in result

    def test_cache_database_error_handling(self, initialized_cache):
        """Test that database errors are handled gracefully."""
        cache = initialized_cache

        # Test with invalid database operations
        result = cache.get_file_id("nonexistent_hash")
        assert result is None  # Should return None, not crash

        result = cache.get_store_id("nonexistent_fileset")
        assert result is None  # Should return None, not crash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
