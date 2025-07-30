"""Integration tests for the vector store lifecycle management."""

import pytest
from unittest.mock import AsyncMock, patch
import time


@pytest.mark.asyncio
class TestVectorStoreLifecycle:
    """Integration tests for the vector store lifecycle management."""

    async def test_cleanup_expired_basic_flow(self, virtual_clock, monkeypatch):
        """Test that the cleanup task works with basic flow."""
        # Patch time functions
        monkeypatch.setattr(time, "time", virtual_clock.time)

        # Import here to avoid circular imports at module level
        from mcp_the_force.vectorstores.manager import VectorStoreManager

        # Create a manager with mocked client
        with patch("mcp_the_force.vectorstores.registry.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            # Mock vector store operations
            mock_store = AsyncMock()
            mock_store.id = "vs_test_123"
            mock_client.create.return_value = mock_store
            mock_client.get.return_value = mock_store
            mock_client.delete = AsyncMock()

            manager = VectorStoreManager(provider="openai")

            # Create some stores
            session_ids = ["expired1", "expired2", "expired3"]
            for session_id in session_ids:
                # Register directly in cache
                await manager.vector_store_cache.register_store(
                    session_id, f"vs_{session_id}", provider="openai"
                )

            # Advance time to expire all stores
            virtual_clock.advance_time(7300)  # Past the 7200s (2hr) default TTL

            # Run cleanup
            cleaned_count = await manager.cleanup_expired()

            # Should have cleaned all 3
            assert cleaned_count == 3
            assert mock_client.delete.call_count == 3

    async def test_session_continuation_after_cleanup(self, virtual_clock, monkeypatch):
        """Test that sessions can continue after vector store cleanup."""
        # Patch time functions
        monkeypatch.setattr(time, "time", virtual_clock.time)

        from mcp_the_force.vectorstores.manager import VectorStoreManager

        with patch("mcp_the_force.vectorstores.registry.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            # Mock vector store
            mock_store = AsyncMock()
            mock_store.id = "vs_phoenix_123"
            mock_client.create.return_value = mock_store
            mock_client.get.return_value = mock_store

            manager = VectorStoreManager(provider="openai")
            session_id = "phoenix-session"

            # Register a store
            await manager.vector_store_cache.register_store(
                session_id, "vs_old_123", provider="openai"
            )

            # Expire and clean it up
            virtual_clock.advance_time(7300)
            cleaned = await manager.cleanup_expired()
            assert cleaned == 1

            # Now try to create a new store for the same session
            # This simulates what happens when a session continues
            result, reused = await manager.vector_store_cache.get_or_create_placeholder(
                session_id
            )
            assert result is None  # No existing store
            assert reused is False

            # Register a new store
            await manager.vector_store_cache.register_store(
                session_id, "vs_new_456", provider="openai"
            )

            # Should be able to retrieve it
            result, reused = await manager.vector_store_cache.get_or_create_placeholder(
                session_id
            )
            assert result == "vs_new_456"
            assert reused is True

    async def test_protected_stores_not_cleaned(self, virtual_clock, monkeypatch):
        """Test that protected stores are never cleaned up."""
        # Patch time functions
        monkeypatch.setattr(time, "time", virtual_clock.time)

        from mcp_the_force.vectorstores.manager import VectorStoreManager

        with patch("mcp_the_force.vectorstores.registry.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.delete = AsyncMock()

            manager = VectorStoreManager(provider="openai")

            # Register normal and protected stores
            await manager.vector_store_cache.register_store(
                "normal", "vs_normal", provider="openai", protected=False
            )
            await manager.vector_store_cache.register_store(
                "protected", "vs_protected", provider="openai", protected=True
            )

            # Expire both
            virtual_clock.advance_time(7300)

            # Run cleanup
            cleaned = await manager.cleanup_expired()

            # Only normal store should be cleaned
            assert cleaned == 1
            assert mock_client.delete.call_count == 1
            mock_client.delete.assert_called_once_with("vs_normal")

    async def test_cleanup_handles_api_errors_gracefully(
        self, virtual_clock, monkeypatch
    ):
        """Test that API errors don't stop the whole cleanup batch."""
        # Patch time functions
        monkeypatch.setattr(time, "time", virtual_clock.time)

        from mcp_the_force.vectorstores.manager import VectorStoreManager

        with patch("mcp_the_force.vectorstores.registry.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            # Make delete fail for specific stores
            async def mock_delete(store_id):
                if store_id == "vs_fail":
                    raise Exception("API Error")
                return None

            mock_client.delete = AsyncMock(side_effect=mock_delete)

            manager = VectorStoreManager(provider="openai")

            # Register stores
            await manager.vector_store_cache.register_store(
                "fail", "vs_fail", provider="openai"
            )
            await manager.vector_store_cache.register_store(
                "success1", "vs_success1", provider="openai"
            )
            await manager.vector_store_cache.register_store(
                "success2", "vs_success2", provider="openai"
            )

            # Expire all
            virtual_clock.advance_time(7300)

            # Run cleanup
            cleaned = await manager.cleanup_expired()

            # Should clean 2 out of 3
            assert cleaned == 2
            assert mock_client.delete.call_count == 3

            # Failed store should still be in cache
            expired = await manager.vector_store_cache.get_expired_stores()
            assert len(expired) == 1
            assert expired[0]["session_id"] == "fail"

    async def test_concurrent_cleanup_operations(
        self, virtual_clock, monkeypatch, tmp_path
    ):
        """Test that cleanup handles many concurrent operations."""
        # Patch time functions
        monkeypatch.setattr(time, "time", virtual_clock.time)

        from mcp_the_force.vectorstores.manager import VectorStoreManager
        from mcp_the_force.vector_store_cache import VectorStoreCache

        with patch("mcp_the_force.vectorstores.registry.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.delete = AsyncMock()

            # Create a manager with isolated cache
            test_db = tmp_path / "test_concurrent.db"
            test_cache = VectorStoreCache(str(test_db), ttl=7200, purge_probability=0.0)
            manager = VectorStoreManager(provider="openai")
            manager.vector_store_cache = test_cache

            # Clean up any existing expired stores first
            await manager.cleanup_expired()

            # Reset the mock call count after initial cleanup
            mock_client.delete.reset_mock()

            # Create many stores
            num_stores = 50
            for i in range(num_stores):
                await manager.vector_store_cache.register_store(
                    f"session_{i}", f"vs_{i}", provider="openai"
                )

            # Expire all
            virtual_clock.advance_time(7300)

            # Run cleanup
            cleaned = await manager.cleanup_expired()

            # All should be cleaned
            assert cleaned == num_stores
            assert mock_client.delete.call_count == num_stores

            # Clean up the test cache
            test_cache.close()

    async def test_background_task_file_lock(self, tmp_path):
        """Test the file lock mechanism for background cleanup."""
        import os

        # Skip on Windows
        if os.name == "nt":
            pytest.skip("File locking test not applicable on Windows")

        # Import fcntl only on Unix
        import fcntl

        lock_file = tmp_path / ".vscleanup.lock"

        # Create and acquire a lock
        with open(lock_file, "w") as f1:
            fcntl.flock(f1.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Try to acquire again - should fail
            with pytest.raises(BlockingIOError):
                with open(lock_file, "w") as f2:
                    fcntl.flock(f2.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
