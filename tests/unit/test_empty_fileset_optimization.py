"""Test for empty fileset optimization in VectorStoreManager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from mcp_the_force.vectorstores.manager import VectorStoreManager


@pytest.mark.asyncio
class TestEmptyFilesetOptimization:
    """Test that empty filesets are optimized to avoid unnecessary API calls."""

    @pytest.fixture
    async def manager(self, tmp_path):
        """Create a VectorStoreManager instance for testing."""
        with patch("mcp_the_force.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.session_db_path = str(tmp_path / "test.db")
            settings.mcp.default_vector_store_provider = "openai"
            settings.adapter_mock = True

            vector_stores = MagicMock()
            vector_stores.ttl_seconds = 7200
            vector_stores.cleanup_probability = 0.0
            settings.vector_stores = vector_stores

            mock_settings.return_value = settings

            manager = VectorStoreManager(provider="openai")
            yield manager
            if hasattr(manager.vector_store_cache, "close"):
                manager.vector_store_cache.close()

    @pytest.fixture
    def mock_client(self):
        """Create a mock vector store client that tracks API calls."""
        client = AsyncMock()
        self._create_call_count = 0

        def track_create_calls(*args, **kwargs):
            """Track create calls and return mock store."""
            self._create_call_count += 1
            mock_store = MagicMock()
            mock_store.id = f"vs_test_{self._create_call_count:03d}"
            mock_store.add_files = AsyncMock()
            return mock_store

        client.create = AsyncMock(side_effect=track_create_calls)
        client.get = AsyncMock()
        client.delete = AsyncMock()

        # Store call count on client for easy access
        client._create_call_count = lambda: self._create_call_count
        return client

    async def test_new_session_empty_files_creates_store(self, manager, mock_client):
        """Test that empty files for NEW session legitimately creates a store."""
        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            # First call with empty files for new session - should create store
            result = await manager.create(
                files=[],  # Empty files
                session_id="new-session-123",
            )

            # Verify store was created
            assert result is not None
            assert result["store_id"] == "vs_test_001"
            assert result["session_id"] == "new-session-123"

            # Verify API call was made
            assert mock_client._create_call_count() == 1

    async def test_existing_session_empty_files_optimization(
        self, manager, mock_client
    ):
        """Test that empty files for EXISTING session avoids API call."""
        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            # First call - create store with files
            result1 = await manager.create(
                files=["dummy_file.txt"],  # Non-empty files
                session_id="existing-session-123",
            )

            initial_call_count = mock_client._create_call_count()
            assert initial_call_count == 1
            store_id_1 = result1["store_id"]

            # Second call - empty files for same session (should be optimized)
            result2 = await manager.create(
                files=[],  # Empty files
                session_id="existing-session-123",
            )

            # Verify same store is returned
            assert result2 is not None
            assert result2["store_id"] == store_id_1
            assert result2["session_id"] == "existing-session-123"

            # Verify NO additional API call was made (optimization worked)
            assert mock_client._create_call_count() == initial_call_count

    async def test_named_stores_not_affected_by_optimization(
        self, manager, mock_client
    ):
        """Test that named stores with empty files are not affected by optimization."""
        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            # Named store with empty files - should always create (for history system)
            result = await manager.create(
                files=[],  # Empty files
                name="project-conversations-001",
            )

            # Verify store was created
            assert result is not None
            assert result["store_id"] == "vs_test_001"
            assert result["name"] == "project-conversations-001"

            # Verify API call was made (no optimization for named stores)
            assert mock_client._create_call_count() == 1

    async def test_optimization_respects_different_sessions(self, manager, mock_client):
        """Test that optimization doesn't interfere with different sessions."""
        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            # Create store for session A
            result_a = await manager.create(files=["file.txt"], session_id="session-a")

            # Empty files for session A - should be optimized
            result_a2 = await manager.create(files=[], session_id="session-a")

            # Empty files for session B - should create new store (new session)
            result_b = await manager.create(files=[], session_id="session-b")

            # Verify results
            assert result_a["store_id"] == result_a2["store_id"]  # Same store reused
            assert (
                result_b["store_id"] != result_a["store_id"]
            )  # Different store for different session

            # Verify call count: 1 for session A, 1 for session B (optimization saved 1 call)
            assert mock_client._create_call_count() == 2

    async def test_optimization_preserves_provider_consistency(
        self, manager, mock_client
    ):
        """Test that optimization returns consistent provider information."""
        with patch(
            "mcp_the_force.vectorstores.registry.get_client", return_value=mock_client
        ):
            # Create initial store
            result1 = await manager.create(
                files=["file.txt"], session_id="provider-test", provider="openai"
            )

            # Optimized call should return same provider
            result2 = await manager.create(files=[], session_id="provider-test")

            # Verify provider consistency
            assert result1["provider"] == result2["provider"]
            assert result1["store_id"] == result2["store_id"]
