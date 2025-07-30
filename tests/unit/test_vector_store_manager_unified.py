"""Unit tests for VectorStoreManager with unified schema."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from mcp_the_force.vectorstores.manager import VectorStoreManager


@pytest.mark.asyncio
class TestVectorStoreManagerUnified:
    """Test VectorStoreManager with unified vector store system."""

    @pytest.fixture
    async def manager(self, tmp_path):
        """Create a VectorStoreManager instance for testing."""
        # Create manager with test database
        with patch("mcp_the_force.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.session_db_path = str(tmp_path / "test.db")
            settings.mcp.default_vector_store_provider = "openai"
            settings.adapter_mock = True  # Enable mock mode for unit tests

            # Mock vector_stores settings
            vector_stores = MagicMock()
            vector_stores.ttl_seconds = 7200
            vector_stores.cleanup_probability = (
                0.0  # Disable probabilistic cleanup in tests
            )
            settings.vector_stores = vector_stores

            mock_settings.return_value = settings

            manager = VectorStoreManager(provider="openai")
            yield manager
            # Cleanup
            if hasattr(manager.vector_store_cache, "close"):
                manager.vector_store_cache.close()

    @pytest.fixture
    def mock_client(self):
        """Create a mock vector store client."""
        client = AsyncMock()
        # Counter for unique IDs
        self._counter = 0

        def create_mock_store(*args, **kwargs):
            """Create a mock store with unique ID."""
            self._counter += 1
            mock_store = MagicMock()
            mock_store.id = f"vs_created{self._counter:03d}"
            mock_store.add_files = AsyncMock()
            return mock_store

        client.create = AsyncMock(side_effect=create_mock_store)
        client.get = AsyncMock(return_value={"id": "vs_created001", "name": "test"})
        client.delete = AsyncMock()
        return client

    async def test_create_with_session_id(self, manager, mock_client):
        """Test creating a session-based vector store."""
        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            # Create session store
            await manager.create(
                files=["file1.txt", "file2.txt"], session_id="test-session-123"
            )

            # Verify client was called
            mock_client.create.assert_called_once()

            # Verify store was registered in cache
            store = await manager.vector_store_cache.get_store(
                session_id="test-session-123"
            )
            assert store is not None
            assert store["vector_store_id"].startswith("vs_created")
            assert store["session_id"] == "test-session-123"
            assert store["name"] is None
            assert store["is_protected"] == 0

    async def test_create_with_name(self, manager, mock_client):
        """Test creating a named vector store."""
        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            # Create named store
            await manager.create(
                files=[], name="project-conversations-001", protected=True
            )

            # Verify client was called
            mock_client.create.assert_called_once()

            # Verify store was registered in cache
            store = await manager.vector_store_cache.get_store(
                name="project-conversations-001"
            )
            assert store is not None
            assert store["vector_store_id"].startswith("vs_created")
            assert store["name"] == "project-conversations-001"
            assert store["session_id"] is None
            assert store["is_protected"] == 1  # Named stores are always protected

    async def test_create_validation(self, manager):
        """Test that create validates parameters correctly."""
        # Test: Must have either session_id or name
        with pytest.raises(
            ValueError, match="Must provide either session_id .* or name"
        ):
            await manager.create(files=[])

        # Test: Cannot have both
        with pytest.raises(ValueError, match="Cannot provide both session_id and name"):
            await manager.create(files=[], session_id="test", name="test")

    async def test_protected_flag_behavior(self, manager, mock_client):
        """Test that protected flag works correctly."""
        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            # Session store with protected=True
            await manager.create(
                files=[], session_id="protected-session", protected=True
            )
            store = await manager.vector_store_cache.get_store(
                session_id="protected-session"
            )
            assert store["is_protected"] == 1

            # Named store ignores protected=False (always protected)
            await manager.create(
                files=[],
                name="always-protected",
                protected=False,  # Should be ignored
            )
            store = await manager.vector_store_cache.get_store(name="always-protected")
            assert store["is_protected"] == 1  # Still protected

    async def test_provider_metadata_handling(self, manager, mock_client):
        """Test provider metadata is passed through correctly."""
        metadata = {"index_type": "hnsw", "m": 16, "ef": 200}

        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            await manager.create(
                files=[], session_id="metadata-test", provider_metadata=metadata
            )

            # Verify metadata was stored
            store = await manager.vector_store_cache.get_store(
                session_id="metadata-test"
            )

            assert store["provider_metadata"] == metadata

    async def test_rollover_from_parameter(self, manager, mock_client):
        """Test rollover_from parameter for memory store lineage."""
        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            # Create first store
            mock_store_old = MagicMock()
            mock_store_old.id = "vs_old001"
            mock_store_old.add_files = AsyncMock()
            mock_client.create.return_value = mock_store_old

            await manager.create(files=[], name="project-memory-001")

            # Create rollover store
            mock_store_new = MagicMock()
            mock_store_new.id = "vs_new001"
            mock_store_new.add_files = AsyncMock()
            mock_client.create.return_value = mock_store_new

            await manager.create(
                files=[], name="project-memory-002", rollover_from="vs_old001"
            )

            # Verify rollover relationship
            new_store = await manager.vector_store_cache.get_store(
                name="project-memory-002"
            )
            assert new_store["rollover_from"] == "vs_old001"

    async def test_ttl_handling(self, manager, mock_client):
        """Test TTL handling for different store types."""
        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            # Session store with custom TTL
            await manager.create(
                files=[],
                session_id="custom-ttl",
                ttl_seconds=3600,  # 1 hour
            )
            store = await manager.vector_store_cache.get_store(session_id="custom-ttl")
            assert store["expires_at"] is not None

            # Named store should have no TTL even if specified
            await manager.create(
                files=[],
                name="no-ttl",
                ttl_seconds=3600,  # Should be ignored
            )
            store = await manager.vector_store_cache.get_store(name="no-ttl")
            assert store["expires_at"] is None

    async def test_backward_compatibility(self, manager, mock_client):
        """Test backward compatibility with existing code."""
        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            # Old-style call with just session_id and files
            result = await manager.create(
                files=["file1.txt"], session_id="legacy-session"
            )

            # Should work without issues
            assert result is not None
            store = await manager.vector_store_cache.get_store(
                session_id="legacy-session"
            )
            assert store["session_id"] == "legacy-session"
            assert store["is_protected"] == 0  # Default

    async def test_cleanup_expired_respects_protected(
        self, manager, virtual_clock, monkeypatch
    ):
        """Test that cleanup doesn't delete protected stores."""
        import time

        monkeypatch.setattr(time, "time", virtual_clock.time)
        # Also patch time in the vector_store_cache module
        import mcp_the_force.vector_store_cache

        monkeypatch.setattr(
            mcp_the_force.vector_store_cache.time, "time", virtual_clock.time
        )
        # And in the sqlite_base_cache module (parent class)
        import mcp_the_force.sqlite_base_cache

        monkeypatch.setattr(
            mcp_the_force.sqlite_base_cache.time, "time", virtual_clock.time
        )

        # Create a shared instance of InMemoryClient for this test
        from mcp_the_force.vectorstores.in_memory import InMemoryClient

        shared_inmemory_client = InMemoryClient()

        # Patch registry to always return the same instance
        with patch("mcp_the_force.vectorstores.registry.get_client") as mock_get_client:
            # Return our shared instance for inmemory, but allow other providers to work normally
            def get_client_side_effect(provider):
                if provider == "inmemory":
                    return shared_inmemory_client
                # For other providers, return a mock (shouldn't be called in mock mode)
                mock = AsyncMock()
                mock.delete = AsyncMock()
                return mock

            mock_get_client.side_effect = get_client_side_effect

            # Create unprotected session store
            await manager.create(
                files=[],
                session_id="temp-store",
                ttl_seconds=60,  # 1 minute
            )

            # Create protected named store
            result2 = await manager.create(files=[], name="permanent-store")

            # Advance time past TTL
            virtual_clock.advance_time(120)  # 2 minutes

            # Run cleanup
            cleaned = await manager.cleanup_expired()

            # Only the unprotected store should be cleaned
            assert cleaned == 1

            # Check that only the protected store remains
            assert len(shared_inmemory_client._stores) == 1
            remaining_store_id = list(shared_inmemory_client._stores.keys())[0]
            assert remaining_store_id == result2["store_id"]
